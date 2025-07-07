import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import random
import time

# إعداد الصفحة
st.set_page_config(
    page_title="CARK Admin Dashboard",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# بيانات وهمية ذكية
def generate_fake_data():
    # بيانات السيارات
    cars_data = [
        {"id": 1, "brand": "Toyota", "model": "Camry", "year": 2022, "status": "pending", "owner": "أحمد محمد", "price": 150, "location": "القاهرة", "created_at": "2024-01-15", "priority": "high"},
        {"id": 2, "brand": "Honda", "model": "Civic", "year": 2021, "status": "approved", "owner": "فاطمة علي", "price": 120, "location": "الإسكندرية", "created_at": "2024-01-10", "priority": "medium"},
        {"id": 3, "brand": "BMW", "model": "X5", "year": 2023, "status": "rejected", "owner": "محمد أحمد", "price": 300, "location": "الجيزة", "created_at": "2024-01-12", "priority": "low"},
        {"id": 4, "brand": "Mercedes", "model": "C-Class", "year": 2022, "status": "pending", "owner": "سارة محمود", "price": 250, "location": "القاهرة", "created_at": "2024-01-14", "priority": "high"},
        {"id": 5, "brand": "Audi", "model": "A4", "year": 2021, "status": "pending", "owner": "علي حسن", "price": 180, "location": "الإسكندرية", "created_at": "2024-01-13", "priority": "medium"},
    ]
    
    # بيانات المستندات
    documents_data = [
        {"id": 1, "type": "رخصة قيادة", "user": "أحمد محمد", "status": "pending", "uploaded_at": "2024-01-15", "expiry_date": "2025-06-15", "priority": "high"},
        {"id": 2, "type": "بطاقة هوية", "user": "فاطمة علي", "status": "approved", "uploaded_at": "2024-01-10", "expiry_date": "2026-03-20", "priority": "medium"},
        {"id": 3, "type": "تأمين السيارة", "user": "محمد أحمد", "status": "rejected", "uploaded_at": "2024-01-12", "expiry_date": "2024-12-31", "priority": "high"},
        {"id": 4, "type": "فحص فني", "user": "سارة محمود", "status": "pending", "uploaded_at": "2024-01-14", "expiry_date": "2024-08-15", "priority": "medium"},
        {"id": 5, "type": "رخصة قيادة", "user": "علي حسن", "status": "pending", "uploaded_at": "2024-01-13", "expiry_date": "2025-01-10", "priority": "low"},
    ]
    
    # بيانات المستخدمين
    users_data = [
        {"id": 1, "name": "أحمد محمد", "email": "ahmed@example.com", "phone": "01012345678", "status": "active", "join_date": "2023-06-15", "rentals_count": 5, "rating": 4.8},
        {"id": 2, "name": "فاطمة علي", "email": "fatima@example.com", "phone": "01087654321", "status": "active", "join_date": "2023-08-20", "rentals_count": 3, "rating": 4.5},
        {"id": 3, "name": "محمد أحمد", "email": "mohamed@example.com", "phone": "01011223344", "status": "suspended", "join_date": "2023-05-10", "rentals_count": 2, "rating": 3.2},
        {"id": 4, "name": "سارة محمود", "email": "sara@example.com", "phone": "01055667788", "status": "active", "join_date": "2023-09-05", "rentals_count": 7, "rating": 4.9},
        {"id": 5, "name": "علي حسن", "email": "ali@example.com", "phone": "01099887766", "status": "pending", "join_date": "2024-01-01", "rentals_count": 0, "rating": 0.0},
    ]
    
    # بيانات الرحلات
    rentals_data = [
        {"id": 1, "car": "Toyota Camry", "renter": "أحمد محمد", "owner": "فاطمة علي", "status": "active", "start_date": "2024-01-15", "end_date": "2024-01-17", "total": 450, "location": "القاهرة"},
        {"id": 2, "car": "Honda Civic", "renter": "محمد أحمد", "owner": "سارة محمود", "status": "completed", "start_date": "2024-01-10", "end_date": "2024-01-12", "total": 360, "location": "الإسكندرية"},
        {"id": 3, "car": "BMW X5", "renter": "علي حسن", "owner": "أحمد محمد", "status": "cancelled", "start_date": "2024-01-12", "end_date": "2024-01-14", "total": 900, "location": "الجيزة"},
        {"id": 4, "car": "Mercedes C-Class", "renter": "سارة محمود", "owner": "محمد أحمد", "status": "active", "start_date": "2024-01-14", "end_date": "2024-01-16", "total": 500, "location": "القاهرة"},
        {"id": 5, "car": "Audi A4", "renter": "فاطمة علي", "owner": "علي حسن", "status": "pending", "start_date": "2024-01-16", "end_date": "2024-01-18", "total": 360, "location": "الإسكندرية"},
    ]
    
    # بيانات البلاغات
    reports_data = [
        {"id": 1, "type": "مشكلة في السيارة", "reporter": "أحمد محمد", "target": "Toyota Camry", "status": "pending", "priority": "high", "created_at": "2024-01-15", "description": "مشكلة في المحرك"},
        {"id": 2, "type": "سلوك غير لائق", "reporter": "فاطمة علي", "target": "محمد أحمد", "status": "resolved", "priority": "medium", "created_at": "2024-01-10", "description": "تأخير في التسليم"},
        {"id": 3, "type": "مشكلة في الدفع", "reporter": "علي حسن", "target": "Honda Civic", "status": "pending", "priority": "high", "created_at": "2024-01-12", "description": "مشكلة في بطاقة الائتمان"},
        {"id": 4, "type": "مخالفة مرورية", "reporter": "سارة محمود", "target": "BMW X5", "status": "investigating", "priority": "high", "created_at": "2024-01-14", "description": "سرعة زائدة"},
        {"id": 5, "type": "مشكلة في الحجز", "reporter": "محمد أحمد", "target": "Mercedes C-Class", "status": "pending", "priority": "low", "created_at": "2024-01-13", "description": "خطأ في التواريخ"},
    ]
    
    return cars_data, documents_data, users_data, rentals_data, reports_data

# تحميل البيانات
cars_data, documents_data, users_data, rentals_data, reports_data = generate_fake_data()

# Sidebar للتنقل
st.sidebar.title("🚗 CARK Admin")
page = st.sidebar.selectbox(
    "اختر الصفحة:",
    ["📊 لوحة التحكم", "🚗 إدارة السيارات", "📄 إدارة المستندات", "👤 إدارة المستخدمين", "🚙 إدارة الرحلات", "⚠️ البلاغات", "⭐ التقييمات", "🔧 الإعدادات"]
)

# الصفحة الرئيسية - لوحة التحكم
if page == "📊 لوحة التحكم":
    st.title("📊 لوحة تحكم CARK")
    
    # إحصائيات سريعة
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("إجمالي المستخدمين", len(users_data), "+12%")
    with col2:
        st.metric("السيارات المعلقة", len([c for c in cars_data if c['status'] == 'pending']), "+3")
    with col3:
        st.metric("البلاغات الجديدة", len([r for r in reports_data if r['status'] == 'pending']), "+5")
    with col4:
        st.metric("الرحلات النشطة", len([r for r in rentals_data if r['status'] == 'active']), "+2")
    
    # رسوم بيانية
    col1, col2 = st.columns(2)
    
    with col1:
        # حالة السيارات
        car_status = pd.DataFrame(cars_data)
        fig1 = px.pie(car_status, names='status', title='حالة السيارات')
        st.plotly_chart(fig1, use_container_width=True)
    
    with col2:
        # حالة البلاغات
        report_status = pd.DataFrame(reports_data)
        fig2 = px.bar(report_status, x='status', title='حالة البلاغات')
        st.plotly_chart(fig2, use_container_width=True)
    
    # تنبيهات ذكية
    st.subheader("🔔 التنبيهات المهمة")
    
    # فحص المستندات المنتهية الصلاحية
    expiring_docs = [d for d in documents_data if d['expiry_date'] < '2024-06-01']
    if expiring_docs:
        st.warning(f"⚠️ {len(expiring_docs)} مستند ستنتهي صلاحيته قريباً")
    
    # فحص البلاغات عالية الأولوية
    high_priority_reports = [r for r in reports_data if r['priority'] == 'high' and r['status'] == 'pending']
    if high_priority_reports:
        st.error(f"🚨 {len(high_priority_reports)} بلاغ عالي الأولوية يحتاج مراجعة فورية")
    
    # اقتراحات ذكية
    st.subheader("💡 اقتراحات ذكية")
    
    # اقتراح مراجعة السيارات المعلقة
    pending_cars = [c for c in cars_data if c['status'] == 'pending']
    if pending_cars:
        st.info(f"📋 مراجعة {len(pending_cars)} سيارة معلقة للموافقة")
    
    # اقتراح مراجعة المستخدمين المعلقين
    pending_users = [u for u in users_data if u['status'] == 'pending']
    if pending_users:
        st.info(f"👤 مراجعة {len(pending_users)} مستخدم معلق")

# صفحة إدارة السيارات
elif page == "🚗 إدارة السيارات":
    st.title("🚗 إدارة السيارات")
    
    # فلترة
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("فلترة حسب الحالة:", ["الكل"] + list(set([c['status'] for c in cars_data])))
    with col2:
        brand_filter = st.selectbox("فلترة حسب الماركة:", ["الكل"] + list(set([c['brand'] for c in cars_data])))
    with col3:
        priority_filter = st.selectbox("فلترة حسب الأولوية:", ["الكل"] + list(set([c['priority'] for c in cars_data])))
    
    # فلترة البيانات
    filtered_cars = cars_data
    if status_filter != "الكل":
        filtered_cars = [c for c in filtered_cars if c['status'] == status_filter]
    if brand_filter != "الكل":
        filtered_cars = [c for c in filtered_cars if c['brand'] == brand_filter]
    if priority_filter != "الكل":
        filtered_cars = [c for c in filtered_cars if c['priority'] == priority_filter]
    
    # عرض البيانات
    if filtered_cars:
        df = pd.DataFrame(filtered_cars)
        
        # إضافة أزرار الإجراءات
        for index, car in enumerate(filtered_cars):
            with st.expander(f"{car['brand']} {car['model']} - {car['owner']}"):
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.write(f"**الحالة:** {car['status']}")
                    st.write(f"**السعر:** {car['price']} جنيه")
                
                with col2:
                    st.write(f"**الموديل:** {car['year']}")
                    st.write(f"**الموقع:** {car['location']}")
                
                with col3:
                    st.write(f"**تاريخ الإضافة:** {car['created_at']}")
                    st.write(f"**الأولوية:** {car['priority']}")
                
                with col4:
                    if car['status'] == 'pending':
                        if st.button(f"✅ موافقة", key=f"approve_{car['id']}"):
                            st.success("تمت الموافقة بنجاح!")
                        if st.button(f"❌ رفض", key=f"reject_{car['id']}"):
                            st.error("تم الرفض!")
                    elif car['status'] == 'rejected':
                        if st.button(f"🔄 إعادة مراجعة", key=f"review_{car['id']}"):
                            st.info("تم إرسالها للمراجعة!")
                    else:
                        st.write("✅ تمت الموافقة")
    else:
        st.info("لا توجد سيارات تطابق المعايير المحددة")

# صفحة إدارة المستندات
elif page == "📄 إدارة المستندات":
    st.title("📄 إدارة المستندات")
    
    # فلترة
    col1, col2, col3 = st.columns(3)
    with col1:
        doc_status_filter = st.selectbox("فلترة حسب الحالة:", ["الكل"] + list(set([d['status'] for d in documents_data])))
    with col2:
        doc_type_filter = st.selectbox("فلترة حسب النوع:", ["الكل"] + list(set([d['type'] for d in documents_data])))
    with col3:
        doc_priority_filter = st.selectbox("فلترة حسب الأولوية:", ["الكل"] + list(set([d['priority'] for d in documents_data])))
    
    # فلترة البيانات
    filtered_docs = documents_data
    if doc_status_filter != "الكل":
        filtered_docs = [d for d in filtered_docs if d['status'] == doc_status_filter]
    if doc_type_filter != "الكل":
        filtered_docs = [d for d in filtered_docs if d['type'] == doc_type_filter]
    if doc_priority_filter != "الكل":
        filtered_docs = [d for d in filtered_docs if d['priority'] == doc_priority_filter]
    
    # تنبيه المستندات المنتهية الصلاحية
    expiring_soon = [d for d in filtered_docs if d['expiry_date'] < '2024-06-01']
    if expiring_soon:
        st.warning(f"⚠️ {len(expiring_soon)} مستند ستنتهي صلاحيته قريباً")
    
    # عرض البيانات
    if filtered_docs:
        df = pd.DataFrame(filtered_docs)
        
        for index, doc in enumerate(filtered_docs):
            with st.expander(f"{doc['type']} - {doc['user']}"):
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.write(f"**النوع:** {doc['type']}")
                    st.write(f"**الحالة:** {doc['status']}")
                
                with col2:
                    st.write(f"**المستخدم:** {doc['user']}")
                    st.write(f"**تاريخ الرفع:** {doc['uploaded_at']}")
                
                with col3:
                    st.write(f"**تاريخ الانتهاء:** {doc['expiry_date']}")
                    st.write(f"**الأولوية:** {doc['priority']}")
                
                with col4:
                    if doc['status'] == 'pending':
                        if st.button(f"✅ موافقة", key=f"doc_approve_{doc['id']}"):
                            st.success("تمت الموافقة على المستند!")
                        if st.button(f"❌ رفض", key=f"doc_reject_{doc['id']}"):
                            st.error("تم رفض المستند!")
                    elif doc['status'] == 'rejected':
                        if st.button(f"🔄 إعادة مراجعة", key=f"doc_review_{doc['id']}"):
                            st.info("تم إرسال المستند للمراجعة!")
                    else:
                        st.write("✅ تمت الموافقة")
                        
                # تنبيه إذا كان المستند سينتهي قريباً
                if doc['expiry_date'] < '2024-06-01':
                    st.warning("⚠️ هذا المستند سينتهي قريباً!")
    else:
        st.info("لا توجد مستندات تطابق المعايير المحددة")

# صفحة إدارة المستخدمين
elif page == "👤 إدارة المستخدمين":
    st.title("👤 إدارة المستخدمين")
    
    # فلترة
    col1, col2 = st.columns(2)
    with col1:
        user_status_filter = st.selectbox("فلترة حسب الحالة:", ["الكل"] + list(set([u['status'] for u in users_data])))
    with col2:
        rating_filter = st.selectbox("فلترة حسب التقييم:", ["الكل", "ممتاز (4.5+)", "جيد (3.5-4.4)", "ضعيف (<3.5)"])
    
    # فلترة البيانات
    filtered_users = users_data
    if user_status_filter != "الكل":
        filtered_users = [u for u in filtered_users if u['status'] == user_status_filter]
    
    if rating_filter == "ممتاز (4.5+)":
        filtered_users = [u for u in filtered_users if u['rating'] >= 4.5]
    elif rating_filter == "جيد (3.5-4.4)":
        filtered_users = [u for u in filtered_users if 3.5 <= u['rating'] < 4.5]
    elif rating_filter == "ضعيف (<3.5)":
        filtered_users = [u for u in filtered_users if u['rating'] < 3.5]
    
    # عرض البيانات
    if filtered_users:
        for user in filtered_users:
            with st.expander(f"{user['name']} - {user['email']}"):
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.write(f"**الاسم:** {user['name']}")
                    st.write(f"**البريد الإلكتروني:** {user['email']}")
                
                with col2:
                    st.write(f"**الهاتف:** {user['phone']}")
                    st.write(f"**الحالة:** {user['status']}")
                
                with col3:
                    st.write(f"**تاريخ الانضمام:** {user['join_date']}")
                    st.write(f"**عدد الرحلات:** {user['rentals_count']}")
                
                with col4:
                    st.write(f"**التقييم:** {user['rating']}/5")
                    
                    if user['status'] == 'active':
                        if st.button(f"🚫 حظر", key=f"ban_{user['id']}"):
                            st.error("تم حظر المستخدم!")
                    elif user['status'] == 'suspended':
                        if st.button(f"✅ تفعيل", key=f"activate_{user['id']}"):
                            st.success("تم تفعيل المستخدم!")
                    elif user['status'] == 'pending':
                        if st.button(f"✅ تفعيل", key=f"approve_{user['id']}"):
                            st.success("تم تفعيل المستخدم!")
                        if st.button(f"❌ رفض", key=f"reject_{user['id']}"):
                            st.error("تم رفض المستخدم!")
    else:
        st.info("لا يوجد مستخدمون يطابقون المعايير المحددة")

# صفحة إدارة الرحلات
elif page == "🚙 إدارة الرحلات":
    st.title("🚙 إدارة الرحلات")
    
    # فلترة
    col1, col2, col3 = st.columns(3)
    with col1:
        rental_status_filter = st.selectbox("فلترة حسب الحالة:", ["الكل"] + list(set([r['status'] for r in rentals_data])))
    with col2:
        location_filter = st.selectbox("فلترة حسب الموقع:", ["الكل"] + list(set([r['location'] for r in rentals_data])))
    with col3:
        date_filter = st.date_input("فلترة حسب التاريخ:", value=datetime.now())
    
    # فلترة البيانات
    filtered_rentals = rentals_data
    if rental_status_filter != "الكل":
        filtered_rentals = [r for r in filtered_rentals if r['status'] == rental_status_filter]
    if location_filter != "الكل":
        filtered_rentals = [r for r in filtered_rentals if r['location'] == location_filter]
    
    # عرض البيانات
    if filtered_rentals:
        for rental in filtered_rentals:
            with st.expander(f"رحلة #{rental['id']} - {rental['car']}"):
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.write(f"**السيارة:** {rental['car']}")
                    st.write(f"**المستأجر:** {rental['renter']}")
                
                with col2:
                    st.write(f"**المالك:** {rental['owner']}")
                    st.write(f"**الحالة:** {rental['status']}")
                
                with col3:
                    st.write(f"**تاريخ البداية:** {rental['start_date']}")
                    st.write(f"**تاريخ النهاية:** {rental['end_date']}")
                
                with col4:
                    st.write(f"**المبلغ الإجمالي:** {rental['total']} جنيه")
                    st.write(f"**الموقع:** {rental['location']}")
                    
                    if rental['status'] == 'active':
                        if st.button(f"⏹️ إيقاف", key=f"stop_{rental['id']}"):
                            st.warning("تم إيقاف الرحلة!")
                    elif rental['status'] == 'pending':
                        if st.button(f"✅ تأكيد", key=f"confirm_{rental['id']}"):
                            st.success("تم تأكيد الرحلة!")
                        if st.button(f"❌ إلغاء", key=f"cancel_{rental['id']}"):
                            st.error("تم إلغاء الرحلة!")
    else:
        st.info("لا توجد رحلات تطابق المعايير المحددة")

# صفحة البلاغات
elif page == "⚠️ البلاغات":
    st.title("⚠️ البلاغات")
    
    # فلترة
    col1, col2, col3 = st.columns(3)
    with col1:
        report_status_filter = st.selectbox("فلترة حسب الحالة:", ["الكل"] + list(set([r['status'] for r in reports_data])))
    with col2:
        report_type_filter = st.selectbox("فلترة حسب النوع:", ["الكل"] + list(set([r['type'] for r in reports_data])))
    with col3:
        report_priority_filter = st.selectbox("فلترة حسب الأولوية:", ["الكل"] + list(set([r['priority'] for r in reports_data])))
    
    # فلترة البيانات
    filtered_reports = reports_data
    if report_status_filter != "الكل":
        filtered_reports = [r for r in filtered_reports if r['status'] == report_status_filter]
    if report_type_filter != "الكل":
        filtered_reports = [r for r in filtered_reports if r['type'] == report_type_filter]
    if report_priority_filter != "الكل":
        filtered_reports = [r for r in filtered_reports if r['priority'] == report_priority_filter]
    
    # تنبيه البلاغات عالية الأولوية
    high_priority = [r for r in filtered_reports if r['priority'] == 'high' and r['status'] == 'pending']
    if high_priority:
        st.error(f"🚨 {len(high_priority)} بلاغ عالي الأولوية يحتاج مراجعة فورية!")
    
    # عرض البيانات
    if filtered_reports:
        for report in filtered_reports:
            # تحديد لون الإطار حسب الأولوية
            if report['priority'] == 'high':
                st.markdown("---")
                st.markdown("### 🚨 بلاغ عالي الأولوية")
            elif report['priority'] == 'medium':
                st.markdown("---")
                st.markdown("### ⚠️ بلاغ متوسط الأولوية")
            else:
                st.markdown("---")
                st.markdown("### ℹ️ بلاغ منخفض الأولوية")
            
            with st.expander(f"{report['type']} - {report['reporter']}"):
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.write(f"**النوع:** {report['type']}")
                    st.write(f"**المبلغ:** {report['reporter']}")
                
                with col2:
                    st.write(f"**الهدف:** {report['target']}")
                    st.write(f"**الحالة:** {report['status']}")
                
                with col3:
                    st.write(f"**الأولوية:** {report['priority']}")
                    st.write(f"**تاريخ البلاغ:** {report['created_at']}")
                
                with col4:
                    st.write(f"**الوصف:** {report['description']}")
                    
                    if report['status'] == 'pending':
                        if st.button(f"✅ حل", key=f"solve_{report['id']}"):
                            st.success("تم حل البلاغ!")
                        if st.button(f"🔍 تحقق", key=f"investigate_{report['id']}"):
                            st.info("تم إرسال البلاغ للتحقيق!")
                    elif report['status'] == 'investigating':
                        if st.button(f"✅ حل", key=f"solve_{report['id']}"):
                            st.success("تم حل البلاغ!")
                        if st.button(f"❌ رفض", key=f"reject_{report['id']}"):
                            st.error("تم رفض البلاغ!")
    else:
        st.info("لا توجد بلاغات تطابق المعايير المحددة")

# صفحة التقييمات
elif page == "⭐ التقييمات":
    st.title("⭐ التقييمات")
    
    # بيانات تقييمات وهمية
    ratings_data = [
        {"id": 1, "rental": "رحلة #1", "renter": "أحمد محمد", "owner": "فاطمة علي", "rating": 5, "comment": "سيارة ممتازة وخدمة رائعة", "date": "2024-01-15"},
        {"id": 2, "rental": "رحلة #2", "renter": "محمد أحمد", "owner": "سارة محمود", "rating": 4, "comment": "جيد جداً", "date": "2024-01-14"},
        {"id": 3, "rental": "رحلة #3", "renter": "علي حسن", "owner": "أحمد محمد", "rating": 2, "comment": "سيارة قديمة ومشكلة في المحرك", "date": "2024-01-13"},
        {"id": 4, "rental": "رحلة #4", "renter": "سارة محمود", "owner": "محمد أحمد", "rating": 5, "comment": "تجربة رائعة", "date": "2024-01-12"},
        {"id": 5, "rental": "رحلة #5", "renter": "فاطمة علي", "owner": "علي حسن", "rating": 3, "comment": "متوسط", "date": "2024-01-11"},
    ]
    
    # فلترة
    col1, col2 = st.columns(2)
    with col1:
        rating_filter = st.selectbox("فلترة حسب التقييم:", ["الكل", "5 نجوم", "4 نجوم", "3 نجوم", "2 نجوم", "1 نجمة"])
    with col2:
        min_rating = st.slider("الحد الأدنى للتقييم:", 1, 5, 1)
    
    # فلترة البيانات
    filtered_ratings = ratings_data
    if rating_filter != "الكل":
        rating_value = int(rating_filter.split()[0])
        filtered_ratings = [r for r in filtered_ratings if r['rating'] == rating_value]
    
    filtered_ratings = [r for r in filtered_ratings if r['rating'] >= min_rating]
    
    # إحصائيات التقييمات
    avg_rating = sum([r['rating'] for r in ratings_data]) / len(ratings_data)
    st.metric("متوسط التقييم العام", f"{avg_rating:.1f}/5")
    
    # عرض البيانات
    if filtered_ratings:
        for rating in filtered_ratings:
            with st.expander(f"تقييم #{rating['id']} - {rating['rental']}"):
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.write(f"**الرحلة:** {rating['rental']}")
                    st.write(f"**المستأجر:** {rating['renter']}")
                
                with col2:
                    st.write(f"**المالك:** {rating['owner']}")
                    st.write(f"**التقييم:** {'⭐' * rating['rating']}")
                
                with col3:
                    st.write(f"**التعليق:** {rating['comment']}")
                    st.write(f"**التاريخ:** {rating['date']}")
                
                with col4:
                    if st.button(f"🗑️ حذف", key=f"delete_{rating['id']}"):
                        st.error("تم حذف التقييم!")
                    if st.button(f"🚫 إخفاء", key=f"hide_{rating['id']}"):
                        st.warning("تم إخفاء التقييم!")
    else:
        st.info("لا توجد تقييمات تطابق المعايير المحددة")

# صفحة الإعدادات
elif page == "🔧 الإعدادات":
    st.title("🔧 إعدادات النظام")
    
    # إعدادات عامة
    st.subheader("⚙️ الإعدادات العامة")
    
    col1, col2 = st.columns(2)
    with col1:
        st.number_input("الحد الأقصى للرحلات اليومية", min_value=1, max_value=100, value=50)
        st.number_input("الحد الأدنى لسن المستخدم", min_value=18, max_value=100, value=21)
        st.number_input("الحد الأقصى لسعر الإيجار اليومي", min_value=100, max_value=10000, value=1000)
    
    with col2:
        st.number_input("مدة صلاحية المستندات (أيام)", min_value=30, max_value=365, value=90)
        st.number_input("الحد الأقصى للبلاغات اليومية", min_value=1, max_value=100, value=20)
        st.selectbox("اللغة الافتراضية", ["العربية", "English"])
    
    # إعدادات الإشعارات
    st.subheader("🔔 إعدادات الإشعارات")
    
    col1, col2 = st.columns(2)
    with col1:
        st.checkbox("إشعارات البريد الإلكتروني", value=True)
        st.checkbox("إشعارات SMS", value=True)
        st.checkbox("إشعارات Push", value=True)
    
    with col2:
        st.checkbox("تنبيهات المستندات المنتهية", value=True)
        st.checkbox("تنبيهات البلاغات العالية", value=True)
        st.checkbox("تقارير يومية", value=True)
    
    # إعدادات الأمان
    st.subheader("🔒 إعدادات الأمان")
    
    col1, col2 = st.columns(2)
    with col1:
        st.number_input("مدة انتهاء الجلسة (دقائق)", min_value=5, max_value=1440, value=30)
        st.number_input("الحد الأقصى لمحاولات تسجيل الدخول", min_value=3, max_value=10, value=5)
        st.checkbox("تفعيل المصادقة الثنائية", value=False)
    
    with col2:
        st.checkbox("تسجيل جميع العمليات", value=True)
        st.checkbox("فحص المستندات تلقائياً", value=True)
        st.checkbox("حماية من هجمات DDoS", value=True)
    
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