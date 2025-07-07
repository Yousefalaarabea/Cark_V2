import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import json
import base64
from PIL import Image
import io

# إعداد الصفحة
st.set_page_config(
    page_title="CARK Admin Dashboard",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# إعدادات API بدون مصادقة
API_BASE_URL = "http://localhost:8000/api/admin"
HEADERS = {
    "Content-Type": "application/json"
}

def make_api_request(endpoint, method="GET", data=None):
    """دالة لإرسال طلبات API"""
    try:
        url = f"{API_BASE_URL}/{endpoint}"
        if method == "GET":
            response = requests.get(url, headers=HEADERS)
        elif method == "POST":
            response = requests.post(url, headers=HEADERS, json=data)
        elif method == "PATCH":
            response = requests.patch(url, headers=HEADERS, json=data)
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"خطأ في API: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        st.error(f"خطأ في الاتصال: {str(e)}")
        return None

def display_image_from_url(image_url):
    """عرض صورة من URL"""
    try:
        if image_url and image_url.startswith('http'):
            response = requests.get(image_url)
            if response.status_code == 200:
                image = Image.open(io.BytesIO(response.content))
                st.image(image, caption="صورة السيارة", use_column_width=True)
            else:
                st.warning("لا يمكن تحميل الصورة")
        else:
            st.warning("رابط الصورة غير صحيح")
    except Exception as e:
        st.warning(f"خطأ في عرض الصورة: {str(e)}")

def display_document_download_button(doc_url, file_name):
    if doc_url and doc_url.startswith('http'):
        if st.button(f"تحميل المستند: {file_name}"):
            response = requests.get(doc_url)
            if response.status_code == 200:
                ext = doc_url.split('.')[-1].lower()
                mime = "application/pdf" if ext == "pdf" else f"image/{ext}" if ext in ["png", "jpg", "jpeg"] else "application/octet-stream"
                st.download_button(
                    label="تحميل المستند",
                    data=response.content,
                    file_name=f"{file_name}.{ext}",
                    mime=mime
                )
            else:
                st.warning("لا يمكن تحميل المستند")
    else:
        st.warning("رابط المستند غير صحيح")

# Sidebar للتنقل
st.sidebar.title("🚗 CARK Admin")
page = st.sidebar.selectbox(
    "اختر الصفحة:",
    ["📊 لوحة التحكم", "🚗 إدارة السيارات", "📄 إدارة المستندات", "👤 إدارة المستخدمين", "🚙 إدارة الرحلات", "⚠️ البلاغات", "⭐ التقييمات", "🔧 الإعدادات"]
)

# الصفحة الرئيسية - لوحة التحكم
if page == "📊 لوحة التحكم":
    st.title("📊 لوحة تحكم CARK")
    
    # الحصول على الإحصائيات
    stats = make_api_request("dashboard/")
    
    if stats:
        # إحصائيات سريعة
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("إجمالي المستخدمين", stats.get('total_users', 0))
        with col2:
            st.metric("السيارات المعلقة", stats.get('pending_cars', 0))
        with col3:
            st.metric("المستندات المعلقة", stats.get('pending_documents', 0))
        with col4:
            st.metric("الرحلات النشطة", stats.get('active_rentals', 0))
        
        # رسوم بيانية
        col1, col2 = st.columns(2)
        
        with col1:
            # حالة السيارات
            cars_data = make_api_request("cars/")
            if cars_data:
                df_cars = pd.DataFrame(cars_data['results'] if 'results' in cars_data else cars_data)
                if not df_cars.empty:
                    fig1 = px.pie(df_cars, names='approval_status', title='حالة السيارات')
                    st.plotly_chart(fig1, use_container_width=True)
        
        with col2:
            # حالة المستندات
            docs_data = make_api_request("documents/")
            if docs_data:
                df_docs = pd.DataFrame(docs_data['results'] if 'results' in docs_data else docs_data)
                if not df_docs.empty:
                    fig2 = px.bar(df_docs, x='status', title='حالة المستندات')
                    st.plotly_chart(fig2, use_container_width=True)
        
        # تنبيهات ذكية
        st.subheader("🔔 التنبيهات المهمة")
        
        # فحص المستندات المنتهية الصلاحية
        if stats.get('expiring_documents', 0) > 0:
            st.warning(f"⚠️ {stats.get('expiring_documents', 0)} مستند ستنتهي صلاحيته قريباً")
        
        # اقتراحات ذكية
        st.subheader("💡 اقتراحات ذكية")
        
        if stats.get('pending_cars', 0) > 0:
            st.info(f"📋 مراجعة {stats.get('pending_cars', 0)} سيارة معلقة للموافقة")
        
        if stats.get('pending_documents', 0) > 0:
            st.info(f"📄 مراجعة {stats.get('pending_documents', 0)} مستند معلق للموافقة")

# صفحة إدارة السيارات
elif page == "🚗 إدارة السيارات":
    st.title("🚗 إدارة السيارات")
    
    # فلترة
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("فلترة حسب الحالة:", ["الكل", "False", "True"])
    with col2:
        brand_filter = st.text_input("فلترة حسب الماركة:")
    with col3:
        owner_filter = st.text_input("فلترة حسب المالك:")
    
    # بناء query parameters
    params = {}
    if status_filter != "الكل":
        params['approval_status'] = status_filter
    if brand_filter:
        params['brand'] = brand_filter
    if owner_filter:
        params['owner'] = owner_filter
    
    # الحصول على البيانات
    cars_data = make_api_request("cars/", data=params)
    
    if cars_data and 'results' in cars_data:
        cars = cars_data['results']
        
        if cars:
            for car in cars:
                with st.expander(f"{car.get('brand', '')} {car.get('model', '')} - {car.get('owner_name', '')}"):
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.write(f"**الحالة:** {car.get('approval_status', '')}")
                        st.write(f"**السعر:** {car.get('price', 0)} جنيه")
                        st.write(f"**الموديل:** {car.get('year', '')}")
                    
                    with col2:
                        st.write(f"**المالك:** {car.get('owner_name', '')}")
                        st.write(f"**الهاتف:** {car.get('owner_phone', '')}")
                        st.write(f"**الموقع:** {car.get('location', '')}")
                    
                    with col3:
                        st.write(f"**تاريخ الإضافة:** {car.get('created_at', '')}")
                        if car.get('verification_status'):
                            st.write(f"**حالة التحقق:** {car.get('verification_status', {}).get('status', '')}")
                    
                    with col4:
                        if car.get('approval_status') == False:
                            if st.button(f"✅ موافقة", key=f"approve_{car.get('id')}"):
                                result = make_api_request(f"cars/{car.get('id')}/approve/", method="POST")
                                if result:
                                    st.success("تمت الموافقة على السيارة بنجاح!")
                                    st.rerun()
                            
                            if st.button(f"❌ رفض", key=f"reject_{car.get('id')}"):
                                rejection_reason = st.text_input("سبب الرفض:", key=f"reason_{car.get('id')}")
                                if rejection_reason:
                                    result = make_api_request(f"cars/{car.get('id')}/reject/", method="POST", data={"rejection_reason": rejection_reason})
                                    if result:
                                        st.success("تم رفض السيارة بنجاح!")
                                        st.rerun()
                        elif car.get('approval_status') == 'rejected':
                            if st.button(f"🔄 إعادة مراجعة", key=f"review_{car.get('id')}"):
                                st.info("تم إرسالها للمراجعة!")
                        else:
                            st.write("✅ تمت الموافقة")
                    
                    # عرض الصور
                    if car.get('images'):
                        st.subheader("🖼️ صور السيارة")
                        for image in car['images']:
                            if image.get('image_url'):
                                display_image_from_url(image['image_url'])
                    
                    # عرض المستندات
                    if car.get('documents'):
                        st.subheader("📄 مستندات السيارة")
                        for doc in car['documents']:
                            st.write(f"**النوع:** {doc.get('document_type', '')}")
                            if doc.get('document_url'):
                                display_document_download_button(doc['document_url'], file_name=f"document_{doc.get('id')}")
        else:
            st.info("لا توجد سيارات تطابق المعايير المحددة")
    else:
        st.error("خطأ في جلب بيانات السيارات")

# صفحة إدارة المستندات
elif page == "📄 إدارة المستندات":
    st.title("📄 إدارة المستندات")
    
    # فلترة
    col1, col2, col3 = st.columns(3)
    with col1:
        doc_status_filter = st.selectbox("فلترة حسب الحالة:", ["الكل", "Pending", "Approved", "Rejected"])
    with col2:
        doc_type_filter = st.text_input("فلترة حسب النوع:")
    with col3:
        user_filter = st.text_input("فلترة حسب المستخدم:")
    
    # بناء query parameters
    params = {}
    if doc_status_filter != "الكل":
        params['status'] = doc_status_filter
    if doc_type_filter:
        params['type'] = doc_type_filter
    if user_filter:
        params['user'] = user_filter
    
    # الحصول على البيانات
    docs_data = make_api_request("documents/", data=params)
    
    if docs_data and 'results' in docs_data:
        documents = docs_data['results']
        
        # تنبيه المستندات المنتهية الصلاحية
        expiring_docs = [doc for doc in documents if doc.get('days_until_expiry', 0) <= 30 and doc.get('days_until_expiry', 0) > 0]
        if expiring_docs:
            st.warning(f"⚠️ {len(expiring_docs)} مستند ستنتهي صلاحيته قريباً")
        
        if documents:
            for doc in documents:
                with st.expander(f"{doc.get('document_type_name', '')} - {(doc.get('user_name') or doc.get('car_plate') or '')}"):
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.write(f"**النوع:** {doc.get('document_type_name', '')}")
                        st.write(f"**الحالة:** {doc.get('status', '')}")
                        if doc.get('comments'):
                            st.write(f"**سبب الرفض/ملاحظات:** {doc.get('comments', '')}")
                    
                    with col2:
                        if doc.get('user_name'):
                            st.write(f"**المستخدم:** {doc.get('user_name', '')}")
                            st.write(f"**الهاتف:** {doc.get('user_phone', '')}")
                        if doc.get('car_id'):
                            st.write(f"**رقم السيارة:** {doc.get('car_id', '')}")
                        if doc.get('car_plate'):
                            st.write(f"**لوحة السيارة:** {doc.get('car_plate', '')}")
                        st.write(f"**تاريخ الرفع:** {doc.get('upload_date', '')}")
                    
                    with col3:
                        st.write(f"**تاريخ الانتهاء:** {doc.get('expiry_date', '')}")
                        if doc.get('days_until_expiry') is not None:
                            days = doc.get('days_until_expiry', 0)
                            if days <= 0:
                                st.error("⚠️ منتهي الصلاحية!")
                            elif days <= 30:
                                st.warning(f"⚠️ ينتهي خلال {days} يوم")
                            else:
                                st.success(f"✅ صالح لمدة {days} يوم")
                    
                    with col4:
                        if doc.get('status') == 'Pending':
                            if st.button(f"✅ موافقة", key=f"doc_approve_{doc.get('id')}"):
                                result = make_api_request(f"documents/{doc.get('id')}/approve/", method="POST")
                                if result:
                                    st.success("تمت الموافقة على المستند بنجاح!")
                                    st.rerun()
                            if st.button(f"❌ رفض", key=f"doc_reject_{doc.get('id')}"):
                                rejection_reason = st.text_input("سبب الرفض:", key=f"doc_reason_{doc.get('id')}")
                                if rejection_reason:
                                    result = make_api_request(f"documents/{doc.get('id')}/reject/", method="POST", data={"rejection_reason": rejection_reason})
                                    if result:
                                        st.success("تم رفض المستند بنجاح!")
                                        st.rerun()
                        elif doc.get('status') == 'Rejected':
                            if st.button(f"🔄 إعادة مراجعة", key=f"doc_review_{doc.get('id')}"):
                                st.info("تم إرسال المستند للمراجعة!")
                        else:
                            st.write("✅ تمت الموافقة")
                    
                    # عرض زر التحميل فقط
                    st.subheader("📄 المستند")
                    if doc.get('document_url'):
                        display_document_download_button(doc['document_url'], file_name=f"document_{doc.get('id')}")
                    else:
                        st.warning("لا يوجد ملف مرفق لهذا المستند.")
        else:
            st.info("لا توجد مستندات تطابق المعايير المحددة")
    else:
        st.error("خطأ في جلب بيانات المستندات")

# صفحة إدارة المستخدمين
elif page == "👤 إدارة المستخدمين":
    st.title("👤 إدارة المستخدمين")
    
    # فلترة
    col1, col2 = st.columns(2)
    with col1:
        user_status_filter = st.selectbox("فلترة حسب الحالة:", ["الكل", "active", "suspended", "pending"])
    with col2:
        min_rating = st.slider("الحد الأدنى للتقييم:", 0.0, 5.0, 0.0)
    
    # بناء query parameters
    params = {}
    if user_status_filter != "الكل":
        params['status'] = user_status_filter
    if min_rating > 0:
        params['min_rating'] = min_rating
    
    # الحصول على البيانات
    users_data = make_api_request("users/", data=params)
    
    if users_data and 'results' in users_data:
        users = users_data['results']
        
        if users:
            for user in users:
                with st.expander(f"{user.get('full_name', '')} - {user.get('email', '')}"):
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.write(f"**الاسم:** {user.get('full_name', '')}")
                        st.write(f"**البريد الإلكتروني:** {user.get('email', '')}")
                    
                    with col2:
                        st.write(f"**الهاتف:** {user.get('phone', '')}")
                        st.write(f"**الحالة:** {user.get('status', '')}")
                    
                    with col3:
                        st.write(f"**تاريخ الانضمام:** {user.get('join_date', '')}")
                        st.write(f"**عدد السيارات:** {user.get('cars_count', 0)}")
                        st.write(f"**عدد الرحلات:** {user.get('rentals_count', 0)}")
                    
                    with col4:
                        st.write(f"**التقييم:** {user.get('avg_rating', 0)}/5")
                        
                        if user.get('status') == 'active':
                            if st.button(f"🚫 حظر", key=f"ban_{user.get('id')}"):
                                reason = st.text_input("سبب الحظر:", key=f"ban_reason_{user.get('id')}")
                                if reason:
                                    result = make_api_request(f"users/{user.get('id')}/suspend/", method="POST", data={"reason": reason})
                                    if result:
                                        st.success("تم حظر المستخدم بنجاح!")
                                        st.rerun()
                        elif user.get('status') == 'suspended':
                            if st.button(f"✅ تفعيل", key=f"activate_{user.get('id')}"):
                                result = make_api_request(f"users/{user.get('id')}/activate/", method="POST")
                                if result:
                                    st.success("تم تفعيل المستخدم بنجاح!")
                                    st.rerun()
                        elif user.get('status') == 'pending':
                            if st.button(f"✅ تفعيل", key=f"approve_{user.get('id')}"):
                                result = make_api_request(f"users/{user.get('id')}/activate/", method="POST")
                                if result:
                                    st.success("تم تفعيل المستخدم بنجاح!")
                                    st.rerun()
        else:
            st.info("لا يوجد مستخدمون يطابقون المعايير المحددة")
    else:
        st.error("خطأ في جلب بيانات المستخدمين")

# صفحة إدارة الرحلات
elif page == "🚙 إدارة الرحلات":
    st.title("🚙 إدارة الرحلات")
    
    # فلترة
    col1, col2, col3 = st.columns(3)
    with col1:
        rental_status_filter = st.selectbox("فلترة حسب الحالة:", ["الكل", "active", "completed", "cancelled", "pending"])
    with col2:
        location_filter = st.text_input("فلترة حسب الموقع:")
    with col3:
        date_filter = st.date_input("فلترة حسب التاريخ:", value=datetime.now())
    
    # بناء query parameters
    params = {}
    if rental_status_filter != "الكل":
        params['status'] = rental_status_filter
    if location_filter:
        params['location'] = location_filter
    if date_filter:
        params['date'] = date_filter.strftime('%Y-%m-%d')
    
    # الحصول على البيانات
    rentals_data = make_api_request("rentals/", data=params)
    
    if rentals_data and 'results' in rentals_data:
        rentals = rentals_data['results']
        
        if rentals:
            for rental in rentals:
                with st.expander(f"رحلة #{rental.get('id')} - {rental.get('car_details', {}).get('brand', '')} {rental.get('car_details', {}).get('model', '')}"):
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.write(f"**السيارة:** {rental.get('car_details', {}).get('brand', '')} {rental.get('car_details', {}).get('model', '')}")
                        st.write(f"**المستأجر:** {rental.get('renter_details', {}).get('full_name', '')}")
                    
                    with col2:
                        st.write(f"**المالك:** {rental.get('owner_details', {}).get('full_name', '')}")
                        st.write(f"**الحالة:** {rental.get('status', '')}")
                    
                    with col3:
                        st.write(f"**تاريخ البداية:** {rental.get('start_date', '')}")
                        st.write(f"**تاريخ النهاية:** {rental.get('end_date', '')}")
                    
                    with col4:
                        st.write(f"**المبلغ الإجمالي:** {rental.get('total', 0)} جنيه")
                        st.write(f"**الموقع:** {rental.get('location', '')}")
                        
                        if rental.get('status') == 'active':
                            if st.button(f"⏹️ إيقاف", key=f"stop_{rental.get('id')}"):
                                st.warning("تم إيقاف الرحلة!")
                        elif rental.get('status') == 'pending':
                            if st.button(f"✅ تأكيد", key=f"confirm_{rental.get('id')}"):
                                st.success("تم تأكيد الرحلة!")
                            if st.button(f"❌ إلغاء", key=f"cancel_{rental.get('id')}"):
                                st.error("تم إلغاء الرحلة!")
        else:
            st.info("لا توجد رحلات تطابق المعايير المحددة")
    else:
        st.error("خطأ في جلب بيانات الرحلات")

# صفحة البلاغات
elif page == "⚠️ البلاغات":
    st.title("⚠️ البلاغات")
    
    # فلترة
    col1, col2, col3 = st.columns(3)
    with col1:
        report_status_filter = st.selectbox("فلترة حسب الحالة:", ["الكل", "pending", "resolved", "investigating"])
    with col2:
        report_type_filter = st.text_input("فلترة حسب النوع:")
    with col3:
        report_priority_filter = st.selectbox("فلترة حسب الأولوية:", ["الكل", "high", "medium", "low"])
    
    # بناء query parameters
    params = {}
    if report_status_filter != "الكل":
        params['status'] = report_status_filter
    if report_type_filter:
        params['type'] = report_type_filter
    if report_priority_filter != "الكل":
        params['priority'] = report_priority_filter
    
    # الحصول على البيانات
    reports_data = make_api_request("reports/", data=params)
    
    if reports_data and 'results' in reports_data:
        reports = reports_data['results']
        
        # تنبيه البلاغات عالية الأولوية
        high_priority = [r for r in reports if r.get('priority') == 'high' and r.get('status') == 'pending']
        if high_priority:
            st.error(f"🚨 {len(high_priority)} بلاغ عالي الأولوية يحتاج مراجعة فورية!")
        
        if reports:
            for report in reports:
                # تحديد لون الإطار حسب الأولوية
                if report.get('priority') == 'high':
                    st.markdown("---")
                    st.markdown("### 🚨 بلاغ عالي الأولوية")
                elif report.get('priority') == 'medium':
                    st.markdown("---")
                    st.markdown("### ⚠️ بلاغ متوسط الأولوية")
                else:
                    st.markdown("---")
                    st.markdown("### ℹ️ بلاغ منخفض الأولوية")
                
                with st.expander(f"{report.get('type', '')} - {report.get('reporter', '')}"):
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.write(f"**النوع:** {report.get('type', '')}")
                        st.write(f"**المبلغ:** {report.get('reporter', '')}")
                    
                    with col2:
                        st.write(f"**الهدف:** {report.get('target', '')}")
                        st.write(f"**الحالة:** {report.get('status', '')}")
                    
                    with col3:
                        st.write(f"**الأولوية:** {report.get('priority', '')}")
                        st.write(f"**تاريخ البلاغ:** {report.get('created_at', '')}")
                    
                    with col4:
                        st.write(f"**الوصف:** {report.get('description', '')}")
                        
                        if report.get('status') == 'pending':
                            if st.button(f"✅ حل", key=f"solve_{report.get('id')}"):
                                result = make_api_request(f"reports/{report.get('id')}/resolve/", method="POST")
                                if result:
                                    st.success("تم حل البلاغ بنجاح!")
                                    st.rerun()
                            if st.button(f"🔍 تحقق", key=f"investigate_{report.get('id')}"):
                                st.info("تم إرسال البلاغ للتحقيق!")
                        elif report.get('status') == 'investigating':
                            if st.button(f"✅ حل", key=f"solve_{report.get('id')}"):
                                st.success("تم حل البلاغ بنجاح!")
                            if st.button(f"❌ رفض", key=f"reject_{report.get('id')}"):
                                st.error("تم رفض البلاغ!")
        else:
            st.info("لا توجد بلاغات تطابق المعايير المحددة")
    else:
        st.error("خطأ في جلب بيانات البلاغات")

# صفحة التقييمات
elif page == "⭐ التقييمات":
    st.title("⭐ التقييمات")
    
    # فلترة
    col1, col2 = st.columns(2)
    with col1:
        rating_filter = st.selectbox("فلترة حسب التقييم:", ["الكل", "5", "4", "3", "2", "1"])
    with col2:
        min_rating = st.slider("الحد الأدنى للتقييم:", 1, 5, 1)
    
    # بناء query parameters
    params = {}
    if rating_filter != "الكل":
        params['rating'] = rating_filter
    if min_rating > 1:
        params['min_rating'] = min_rating
    
    # الحصول على البيانات
    ratings_data = make_api_request("ratings/", data=params)
    
    if ratings_data and 'results' in ratings_data:
        ratings = ratings_data['results']
        
        # إحصائيات التقييمات
        if ratings:
            avg_rating = sum([r.get('rating', 0) for r in ratings]) / len(ratings)
            st.metric("متوسط التقييم العام", f"{avg_rating:.1f}/5")
        
        if ratings:
            for rating in ratings:
                with st.expander(f"تقييم #{rating.get('id')} - {rating.get('rental', '')}"):
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.write(f"**الرحلة:** {rating.get('rental', '')}")
                        st.write(f"**المستأجر:** {rating.get('renter_name', '')}")
                    
                    with col2:
                        st.write(f"**المالك:** {rating.get('owner_name', '')}")
                        st.write(f"**التقييم:** {'⭐' * rating.get('rating', 0)}")
                    
                    with col3:
                        st.write(f"**التعليق:** {rating.get('comment', '')}")
                        st.write(f"**التاريخ:** {rating.get('created_at', '')}")
                    
                    with col4:
                        if st.button(f"🗑️ حذف", key=f"delete_{rating.get('id')}"):
                            result = make_api_request(f"ratings/{rating.get('id')}/delete/", method="POST")
                            if result:
                                st.success("تم حذف التقييم بنجاح!")
                                st.rerun()
                        if st.button(f"🚫 إخفاء", key=f"hide_{rating.get('id')}"):
                            st.warning("تم إخفاء التقييم!")
        else:
            st.info("لا توجد تقييمات تطابق المعايير المحددة")
    else:
        st.error("خطأ في جلب بيانات التقييمات")

# صفحة الإعدادات
elif page == "🔧 الإعدادات":
    st.title("🔧 إعدادات النظام")
    
    # إعدادات عامة
    st.subheader("⚙️ الإعدادات العامة")
    
    col1, col2 = st.columns(2)
    with col1:
        max_daily_rentals = st.number_input("الحد الأقصى للرحلات اليومية", min_value=1, max_value=100, value=50)
        min_user_age = st.number_input("الحد الأدنى لسن المستخدم", min_value=18, max_value=100, value=21)
        max_daily_price = st.number_input("الحد الأقصى لسعر الإيجار اليومي", min_value=100, max_value=10000, value=1000)
    
    with col2:
        doc_expiry_days = st.number_input("مدة صلاحية المستندات (أيام)", min_value=30, max_value=365, value=90)
        max_daily_reports = st.number_input("الحد الأقصى للبلاغات اليومية", min_value=1, max_value=100, value=20)
        default_language = st.selectbox("اللغة الافتراضية", ["العربية", "English"])
    
    # إعدادات الإشعارات
    st.subheader("🔔 إعدادات الإشعارات")
    
    col1, col2 = st.columns(2)
    with col1:
        email_notifications = st.checkbox("إشعارات البريد الإلكتروني", value=True)
        sms_notifications = st.checkbox("إشعارات SMS", value=True)
        push_notifications = st.checkbox("إشعارات Push", value=True)
    
    with col2:
        expiring_doc_alerts = st.checkbox("تنبيهات المستندات المنتهية", value=True)
        high_priority_alerts = st.checkbox("تنبيهات البلاغات العالية", value=True)
        daily_reports = st.checkbox("تقارير يومية", value=True)
    
    # إعدادات الأمان
    st.subheader("🔒 إعدادات الأمان")
    
    col1, col2 = st.columns(2)
    with col1:
        session_timeout = st.number_input("مدة انتهاء الجلسة (دقائق)", min_value=5, max_value=1440, value=30)
        max_login_attempts = st.number_input("الحد الأقصى لمحاولات تسجيل الدخول", min_value=3, max_value=10, value=5)
        two_factor_auth = st.checkbox("تفعيل المصادقة الثنائية", value=False)
    
    with col2:
        activity_logging = st.checkbox("تسجيل جميع العمليات", value=True)
        auto_doc_scan = st.checkbox("فحص المستندات تلقائياً", value=True)
        ddos_protection = st.checkbox("حماية من هجمات DDoS", value=True)
    
    # أزرار الحفظ
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("💾 حفظ الإعدادات"):
            st.success("تم حفظ الإعدادات بنجاح!")
    with col2:
        if st.button("🔄 إعادة تعيين"):
            st.info("تم إعادة تعيين الإعدادات!")
    with col3:
        if st.button("📤 تصدير الإعدادات"):
            st.info("تم تصدير الإعدادات!")

# Footer
st.markdown("---")
st.markdown("**CARK Admin Dashboard** - تم التطوير بواسطة فريق CARK")

# إضافة معلومات الاتصال
st.sidebar.markdown("---")
st.sidebar.markdown("### 📞 معلومات الاتصال")
st.sidebar.markdown("**البريد الإلكتروني:** admin@cark.com")
st.sidebar.markdown("**الهاتف:** +20 123 456 7890")
st.sidebar.markdown("**الدعم الفني:** 24/7") 