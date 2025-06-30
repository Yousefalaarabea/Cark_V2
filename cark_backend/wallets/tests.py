from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from .models import Wallet, WalletTransaction, WalletRecharge, WalletWithdrawal, TransactionType
from .services import WalletService, WalletRechargeService, WalletWithdrawalService

User = get_user_model()

class WalletModelTest(TestCase):
    """اختبارات نموذج المحفظة"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
            phone_number='0123456789',
            national_id='12345678901234'
        )
        # المحفظة يتم إنشاؤها تلقائياً عبر signals
        self.wallet = self.user.wallet
    
    def test_wallet_creation(self):
        """اختبار إنشاء المحفظة"""
        self.assertEqual(self.wallet.user, self.user)
        self.assertEqual(self.wallet.balance, Decimal('0.00'))
        self.assertTrue(self.wallet.is_active)
    
    def test_add_funds(self):
        """اختبار إضافة أموال للمحفظة"""
        initial_balance = self.wallet.balance
        self.wallet.add_funds(Decimal('50.00'))
        self.assertEqual(self.wallet.balance, initial_balance + Decimal('50.00'))
    
    def test_deduct_funds(self):
        """اختبار خصم أموال من المحفظة"""
        # إضافة أموال أولاً
        self.wallet.add_funds(Decimal('100.00'))
        initial_balance = self.wallet.balance
        self.wallet.deduct_funds(Decimal('30.00'))
        self.assertEqual(self.wallet.balance, initial_balance - Decimal('30.00'))
    
    def test_deduct_funds_insufficient_balance(self):
        """اختبار خصم أموال برصيد غير كافي"""
        with self.assertRaises(Exception):
            self.wallet.deduct_funds(Decimal('200.00'))

class WalletServiceTest(TestCase):
    """اختبارات خدمة المحفظة"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
            phone_number='0123456789',
            national_id='12345678901234'
        )
        self.transaction_type = TransactionType.objects.create(
            name='شحن محفظة',
            description='إضافة أموال للمحفظة',
            is_credit=True
        )
    
    def test_get_or_create_wallet(self):
        """اختبار الحصول على محفظة أو إنشاء واحدة جديدة"""
        wallet = WalletService.get_or_create_wallet(self.user)
        self.assertIsInstance(wallet, Wallet)
        self.assertEqual(wallet.user, self.user)
        
        # اختبار الحصول على نفس المحفظة مرة أخرى
        wallet2 = WalletService.get_or_create_wallet(self.user)
        self.assertEqual(wallet.id, wallet2.id)
    
    def test_add_funds_to_wallet(self):
        """اختبار إضافة أموال للمحفظة عبر الخدمة"""
        transaction = WalletService.add_funds_to_wallet(
            self.user, 
            Decimal('100.00'), 
            'شحن محفظة',
            'شحن عبر البطاقة'
        )
        
        self.assertIsInstance(transaction, WalletTransaction)
        self.assertEqual(transaction.amount, Decimal('100.00'))
        self.assertEqual(transaction.status, 'completed')
        
        # التحقق من تحديث رصيد المحفظة
        wallet = WalletService.get_or_create_wallet(self.user)
        self.assertEqual(wallet.balance, Decimal('100.00'))
    
    def test_deduct_funds_from_wallet(self):
        """اختبار خصم أموال من المحفظة عبر الخدمة"""
        # إضافة أموال أولاً
        WalletService.add_funds_to_wallet(self.user, Decimal('200.00'), 'شحن محفظة')
        
        # خصم أموال
        transaction = WalletService.deduct_funds_from_wallet(
            self.user, 
            Decimal('50.00'), 
            'دفع إيجار',
            'دفع إيجار السيارة'
        )
        
        self.assertIsInstance(transaction, WalletTransaction)
        self.assertEqual(transaction.amount, Decimal('50.00'))
        self.assertEqual(transaction.status, 'completed')
        
        # التحقق من تحديث رصيد المحفظة
        wallet = WalletService.get_or_create_wallet(self.user)
        self.assertEqual(wallet.balance, Decimal('150.00'))
    
    def test_transfer_between_wallets(self):
        """اختبار التحويل بين المحافظ"""
        recipient = User.objects.create_user(
            email='recipient@example.com',
            password='testpass123',
            first_name='Recipient',
            last_name='User',
            phone_number='0987654321',
            national_id='98765432109876'
        )
        
        # إضافة أموال للمرسل
        WalletService.add_funds_to_wallet(self.user, Decimal('100.00'), 'شحن محفظة')
        
        # التحويل
        result = WalletService.transfer_between_wallets(
            self.user,
            recipient.email,
            Decimal('30.00'),
            'تحويل تجريبي'
        )
        
        self.assertIn('debit_transaction', result)
        self.assertIn('credit_transaction', result)
        
        # التحقق من رصيد المرسل
        sender_wallet = WalletService.get_or_create_wallet(self.user)
        self.assertEqual(sender_wallet.balance, Decimal('70.00'))
        
        # التحقق من رصيد المستلم
        recipient_wallet = WalletService.get_or_create_wallet(recipient)
        self.assertEqual(recipient_wallet.balance, Decimal('30.00'))

class WalletRechargeServiceTest(TestCase):
    """اختبارات خدمة شحن المحفظة"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
            phone_number='0123456789',
            national_id='12345678901234'
        )
    
    def test_create_recharge_request(self):
        """اختبار إنشاء طلب شحن"""
        recharge = WalletRechargeService.create_recharge_request(
            self.user,
            Decimal('100.00'),
            'card',
            'شحن عبر البطاقة'
        )
        
        self.assertIsInstance(recharge, WalletRecharge)
        self.assertEqual(recharge.amount, Decimal('100.00'))
        self.assertEqual(recharge.method, 'card')
        self.assertEqual(recharge.status, 'pending')

class WalletWithdrawalServiceTest(TestCase):
    """اختبارات خدمة سحب من المحفظة"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
            phone_number='0123456789',
            national_id='12345678901234'
        )
        # إضافة أموال للمحفظة
        WalletService.add_funds_to_wallet(self.user, Decimal('200.00'), 'شحن محفظة')
    
    def test_create_withdrawal_request(self):
        """اختبار إنشاء طلب سحب"""
        withdrawal = WalletWithdrawalService.create_withdrawal_request(
            self.user,
            Decimal('50.00'),
            'bank_transfer',
            '1234567890',
            'بنك مصر',
            'سحب للبنك'
        )
        
        self.assertIsInstance(withdrawal, WalletWithdrawal)
        self.assertEqual(withdrawal.amount, Decimal('50.00'))
        self.assertEqual(withdrawal.method, 'bank_transfer')
        self.assertEqual(withdrawal.status, 'pending')
    
    def test_create_withdrawal_request_insufficient_balance(self):
        """اختبار إنشاء طلب سحب برصيد غير كافي"""
        with self.assertRaises(ValueError):
            WalletWithdrawalService.create_withdrawal_request(
                self.user,
                Decimal('300.00'),
                'bank_transfer'
            )
    
    def test_process_withdrawal(self):
        """اختبار معالجة طلب السحب"""
        withdrawal = WalletWithdrawalService.create_withdrawal_request(
            self.user,
            Decimal('50.00'),
            'bank_transfer'
        )
        
        result = WalletWithdrawalService.process_withdrawal(withdrawal.id)
        
        self.assertIn('withdrawal', result)
        self.assertIn('wallet_transaction', result)
        self.assertEqual(result['withdrawal'].status, 'completed')
        
        # التحقق من تحديث رصيد المحفظة
        wallet = WalletService.get_or_create_wallet(self.user)
        self.assertEqual(wallet.balance, Decimal('150.00'))

class WalletTransactionTest(TestCase):
    """اختبارات معاملات المحفظة"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
            phone_number='0123456789',
            national_id='12345678901234'
        )
        self.wallet = WalletService.get_or_create_wallet(self.user)
        self.transaction_type = TransactionType.objects.create(
            name='شحن محفظة',
            description='إضافة أموال للمحفظة',
            is_credit=True
        )
    
    def test_wallet_transaction_creation(self):
        """اختبار إنشاء معاملة محفظة"""
        transaction = WalletTransaction.objects.create(
            wallet=self.wallet,
            transaction_type=self.transaction_type,
            amount=Decimal('100.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('100.00'),
            status='completed',
            description='معاملة تجريبية'
        )
        
        self.assertEqual(transaction.wallet, self.wallet)
        self.assertEqual(transaction.amount, Decimal('100.00'))
        self.assertEqual(transaction.status, 'completed')
        self.assertEqual(transaction.balance_before, Decimal('0.00'))
        self.assertEqual(transaction.balance_after, Decimal('100.00'))
