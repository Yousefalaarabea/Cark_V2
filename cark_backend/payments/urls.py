from django.urls import path, include
from .views import StartPaymentView , paymob_webhook,SavedCardsView, AddSavedCardView, ListPaymentMethodsView, PayView, AdminPaymentTransactionsView, ChargeSavedCardView
from django.http import JsonResponse


# router = DefaultRouter()
# router.register('transactions', PaymentTransactionViewSet, basename='transaction')
# router.register('cards', SavedCardViewSet, basename='savedcard')

urlpatterns = [
    path("start/", StartPaymentView.as_view(), name="start_payment"),
    path("webhook/", paymob_webhook, name="paymob_webhook"),
    path("saved-cards/", SavedCardsView.as_view(), name="saved_cards"), 
    path('add-card/', AddSavedCardView.as_view(), name='add-saved-card'),
    path('payment-methods/', ListPaymentMethodsView.as_view(), name='list-payment-methods'),
    path('pay/', PayView.as_view(), name='pay'),
    path('admin/transactions/', AdminPaymentTransactionsView.as_view(), name='admin-payment-transactions'),
    path('charge-saved-card/', ChargeSavedCardView.as_view(), name='charge-saved-card'),
    # path("", include(router.urls)),  # this includes the /cards/ and /transactions/ endpoints
    path('test/', lambda request: JsonResponse({'ok': True})),

]

