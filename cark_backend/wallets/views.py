from django.shortcuts import render
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db import models
from decimal import Decimal

from .models import Wallet, WalletTransaction, WalletRecharge, WalletWithdrawal, TransactionType
from .serializers import (
    WalletSerializer, WalletTransactionSerializer, WalletRechargeSerializer,
    WalletWithdrawalSerializer, WalletBalanceSerializer, WalletTransactionHistorySerializer,
    WalletRechargeRequestSerializer, WalletWithdrawalRequestSerializer, WalletTransferSerializer,
    WithdrawAllToMobileWalletSerializer, WalletPhoneNumberSerializer
)
from .services import (
    WalletService, WalletRechargeService, WalletWithdrawalService, WalletTransactionService
)

User = get_user_model()

class WalletBalanceView(APIView):
    """عرض رصيد المحفظة"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """الحصول على رصيد المحفظة"""
        try:
            wallet = WalletService.get_or_create_wallet(request.user)
            serializer = WalletBalanceSerializer(wallet)
            return Response({
                'success': True,
                'data': serializer.data
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class WalletTransactionHistoryView(generics.ListAPIView):
    """عرض تاريخ معاملات المحفظة"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WalletTransactionHistorySerializer
    
    def get_queryset(self):
        """الحصول على معاملات المستخدم"""
        limit = int(self.request.query_params.get('limit', 50))
        offset = int(self.request.query_params.get('offset', 0))
        return WalletTransactionService.get_user_transactions(self.request.user, limit, offset)

class WalletTransactionSummaryView(APIView):
    """ملخص معاملات المحفظة"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """الحصول على ملخص المعاملات"""
        try:
            days = int(request.query_params.get('days', 30))
            summary = WalletTransactionService.get_transaction_summary(request.user, days)
            return Response({
                'success': True,
                'data': summary
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class WalletRechargeView(APIView):
    """شحن المحفظة"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """إنشاء طلب شحن"""
        try:
            serializer = WalletRechargeRequestSerializer(data=request.data)
            if serializer.is_valid():
                recharge = WalletRechargeService.create_recharge_request(
                    user=request.user,
                    amount=serializer.validated_data['amount'],
                    method=serializer.validated_data['method'],
                    description=serializer.validated_data.get('description', '')
                )
                
                # إذا كان الشحن بالبطاقة، قم بإنشاء معاملة دفع
                if recharge.method == 'card':
                    from payments.services.paymob import PaymobService
                    payment_data = {
                        'amount_cents': int(recharge.amount * 100),  # تحويل للقروش
                        'currency': 'EGP',
                        'merchant_order_id': f"wallet_recharge_{recharge.id}",
                        'user': request.user,
                        'description': f"شحن محفظة - {recharge.amount} جنيه"
                    }
                    
                    # payment_transaction = PaymentTransaction.objects.create(...)
                    payment_response = PaymobService.create_payment_intent(payment_data)
                    
                    return Response({
                        'success': True,
                        'data': {
                            'recharge': WalletRechargeSerializer(recharge).data,
                            'payment_url': payment_response.get('payment_url'),
                            'payment_id': payment_response.get('payment_id')
                        }
                    })
                
                return Response({
                    'success': True,
                    'data': WalletRechargeSerializer(recharge).data,
                    'message': 'تم إنشاء طلب الشحن بنجاح'
                })
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class WalletWithdrawalView(APIView):
    """سحب من المحفظة (خصم فوري)"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            serializer = WalletWithdrawalRequestSerializer(data=request.data)
            if serializer.is_valid():
                wallet = request.user.wallet
                amount = serializer.validated_data['amount']
                # استخدم الرقم المرسل أو الرقم المسجل
                phone_number = request.data.get('phone_number') or wallet.phone_wallet_number
                if not phone_number:
                    return Response({'success': False, 'error': 'يجب إدخال رقم محفظة الهاتف أو تسجيله أولاً.'}, status=400)
                if wallet.balance < amount:
                    return Response({'success': False, 'error': 'الرصيد غير كافٍ'}, status=400)
                # خصم الرصيد مباشرة
                from wallets.services import WalletService
                WalletService.deduct_funds_from_wallet(
                    user=request.user,
                    amount=amount,
                    transaction_type_name='سحب من محفظة',
                    description=serializer.validated_data.get('description', ''),
                    reference_type='withdrawal'
                )
                wallet.refresh_from_db()
                # إنشاء سجل السحب بحالة مكتملة مع رقم المحفظة المستخدم
                withdrawal = WalletWithdrawal.objects.create(
                    wallet=wallet,
                    amount=amount,
                    method=serializer.validated_data['method'],
                    status='completed',
                    bank_account=phone_number,  # هنا يتم حفظ رقم المحفظة في bank_account
                    bank_name=serializer.validated_data.get('bank_name', ''),
                    description=serializer.validated_data.get('description', '')
                )
                return Response({
                    'success': True,
                    'data': WalletWithdrawalSerializer(withdrawal).data,
                    'new_balance': str(wallet.balance),
                    'message': 'تم سحب المبلغ بنجاح',
                    'used_phone_number': phone_number
                })
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class WalletTransferView(APIView):
    """تحويل بين المحافظ"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """تحويل أموال لمستخدم آخر"""
        try:
            serializer = WalletTransferSerializer(data=request.data)
            if serializer.is_valid():
                result = WalletService.transfer_between_wallets(
                    sender=request.user,
                    recipient_email=serializer.validated_data['recipient_email'],
                    amount=serializer.validated_data['amount'],
                    description=serializer.validated_data.get('description', '')
                )
                
                return Response({
                    'success': True,
                    'data': {
                        'debit_transaction': WalletTransactionSerializer(result['debit_transaction']).data,
                        'credit_transaction': WalletTransactionSerializer(result['credit_transaction']).data
                    },
                    'message': 'تم التحويل بنجاح'
                })
            else:
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

# Admin Views
class AdminWalletListView(generics.ListAPIView):
    """قائمة المحافظ (للإدارة)"""
    permission_classes = [permissions.IsAdminUser]
    serializer_class = WalletSerializer
    queryset = Wallet.objects.all()

class AdminWalletDetailView(generics.RetrieveAPIView):
    """تفاصيل محفظة معينة (للإدارة)"""
    permission_classes = [permissions.IsAdminUser]
    serializer_class = WalletSerializer
    queryset = Wallet.objects.all()

class AdminUserWalletDetailView(APIView):
    """تفاصيل محفظة مستخدم معين (للإدارة)"""
    permission_classes = [permissions.IsAdminUser]
    
    def get(self, request, user_id):
        """الحصول على تفاصيل محفظة مستخدم معين"""
        try:
            from users.models import User
            user = User.objects.get(id=user_id)
            wallet = WalletService.get_or_create_wallet(user)
            
            # الحصول على المعاملات الأخيرة
            transactions = WalletTransaction.objects.filter(
                wallet=wallet
            ).order_by('-created_at')[:10]
            
            # حساب الإحصائيات
            total_credit = WalletTransaction.objects.filter(
                wallet=wallet,
                transaction_type__is_credit=True
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            
            total_debit = WalletTransaction.objects.filter(
                wallet=wallet,
                transaction_type__is_credit=False
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            
            return Response({
                'success': True,
                'data': {
                    'user': {
                        'id': user.id,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'phone_number': user.phone_number
                    },
                    'wallet': {
                        'id': wallet.id,
                        'balance': wallet.balance,
                        'is_active': wallet.is_active,
                        'created_at': wallet.created_at,
                        'updated_at': wallet.updated_at
                    },
                    'transactions': WalletTransactionSerializer(transactions, many=True).data,
                    'statistics': {
                        'total_transactions': WalletTransaction.objects.filter(wallet=wallet).count(),
                        'total_credit': total_credit,
                        'total_debit': total_debit,
                        'net_amount': total_credit - total_debit
                    }
                }
            })
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': 'المستخدم غير موجود'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class AdminWithdrawalListView(generics.ListAPIView):
    """قائمة طلبات السحب (للإدارة)"""
    permission_classes = [permissions.IsAdminUser]
    serializer_class = WalletWithdrawalSerializer
    queryset = WalletWithdrawal.objects.all()

class AdminWithdrawalProcessView(APIView):
    """معالجة طلب سحب (للإدارة)"""
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request, withdrawal_id):
        """معالجة طلب السحب"""
        try:
            result = WalletWithdrawalService.process_withdrawal(withdrawal_id, request.user)
            return Response({
                'success': True,
                'data': {
                    'withdrawal': WalletWithdrawalSerializer(result['withdrawal']).data,
                    'wallet_transaction': WalletTransactionSerializer(result['wallet_transaction']).data
                },
                'message': 'تم معالجة طلب السحب بنجاح'
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class AdminWithdrawalCancelView(APIView):
    """إلغاء طلب سحب (للإدارة)"""
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request, withdrawal_id):
        """إلغاء طلب السحب"""
        try:
            withdrawal = WalletWithdrawalService.cancel_withdrawal(withdrawal_id, request.user)
            return Response({
                'success': True,
                'data': WalletWithdrawalSerializer(withdrawal).data,
                'message': 'تم إلغاء طلب السحب بنجاح'
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

# Webhook for payment processing
@api_view(['POST'])
@permission_classes([])
def wallet_payment_webhook(request):
    """Webhook لمعالجة دفع شحن المحفظة"""
    try:
        # استقبال بيانات الدفع من Paymob
        payment_data = request.data
        
        # البحث عن معاملة الدفع
        from payments.models import PaymentTransaction
        # payment_transaction = PaymentTransaction.objects.get(
        #     paymob_transaction_id=payment_data.get('transaction_id')
        # )
        
        # البحث عن طلب الشحن المرتبط
        recharge = WalletRecharge.objects.get(
            payment_transaction=payment_transaction
        )
        
        # معالجة الشحن
        result = WalletRechargeService.process_recharge_payment(recharge.id, payment_transaction)
        
        return Response({
            'success': True,
            'message': 'تم معالجة الدفع بنجاح'
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)

class WithdrawAllToMobileWalletView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = WithdrawAllToMobileWalletSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)
        # استخدم الرقم المرسل أو الرقم المسجل
        phone_number = serializer.validated_data.get('phone_number') or request.user.wallet.phone_wallet_number
        if not phone_number:
            return Response({'success': False, 'error': 'يجب إدخال رقم محفظة الهاتف أو تسجيله أولاً.'}, status=400)
        description = serializer.validated_data.get('description', 'تحويل كل الرصيد')
        balance = request.user.wallet.balance
        if balance <= 0:
            return Response({'success': False, 'error': 'لا يوجد رصيد كافٍ'}, status=400)
        try:
            transaction = WalletService.deduct_funds_from_wallet(
                user=request.user,
                amount=balance,
                transaction_type_name='تحويل لمحفظة الهاتف',
                description=description,
                reference_type='mobile_wallet'
            )
            return Response({'success': True, 'amount_transferred': str(balance), 'transaction_id': str(transaction.id), 'used_phone_number': phone_number})
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=400)

class SetWalletPhoneNumberView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = WalletPhoneNumberSerializer(data=request.data)
        if serializer.is_valid():
            wallet = request.user.wallet
            if wallet.phone_wallet_number:
                return Response({'success': False, 'error': 'رقم المحفظة مسجل بالفعل. يمكنك تعديله فقط.'}, status=400)
            wallet.phone_wallet_number = serializer.validated_data['phone_wallet_number']
            wallet.save()
            return Response({'success': True, 'phone_wallet_number': wallet.phone_wallet_number})
        return Response({'success': False, 'errors': serializer.errors}, status=400)

    def put(self, request):
        serializer = WalletPhoneNumberSerializer(data=request.data)
        if serializer.is_valid():
            wallet = request.user.wallet
            wallet.phone_wallet_number = serializer.validated_data['phone_wallet_number']
            wallet.save()
            return Response({'success': True, 'phone_wallet_number': wallet.phone_wallet_number})
        return Response({'success': False, 'errors': serializer.errors}, status=400)
