from django.contrib.auth import get_user_model
from .models import Notification
from django.utils import timezone

User = get_user_model()

class NotificationService:
    """Service class for handling notifications"""
    
    @staticmethod
    def send_booking_request_notification(rental):
        """
        Send booking request notification to car owner
        
        Args:
            rental: SelfDriveRental instance
        """
        try:
            # Get car owner
            car_owner = rental.car.owner
            
            # Get renter details
            renter = rental.renter
            renter_name = f"{renter.first_name} {renter.last_name}".strip() or renter.email
            
            # Get car details
            car = rental.car
            car_name = f"{car.brand} {car.model}"
            
            # Create notification data
            notification_data = {
                "renterId": rental.renter.id,
                "carId": rental.car.id,
                "status": rental.status,
                "rentalId": rental.id,
                "startDate": rental.start_date.isoformat(),
                "endDate": rental.end_date.isoformat(),
                "pickupAddress": rental.pickup_address,
                "dropoffAddress": rental.dropoff_address,
                "renterName": renter_name,
                "carName": car_name,
                "dailyPrice": float(rental.car.rental_options.daily_rental_price) if rental.car.rental_options.daily_rental_price else 0,
                "totalDays": (rental.end_date.date() - rental.start_date.date()).days + 1,
                "totalAmount": float(rental.payment.rental_total_amount) if hasattr(rental, 'payment') else 0,
                "depositAmount": float(rental.payment.deposit_amount) if hasattr(rental, 'payment') else 0,
            }
            
            # Create notification
            notification = Notification.objects.create( # type: ignore
                sender=rental.renter,  # Renter is the sender
                receiver=car_owner,    # Car owner is the receiver
                title="New Booking Request",
                message=f"{renter_name} has requested to rent your {car_name}",
                notification_type="RENTAL",
                priority="HIGH",
                data=notification_data,
                is_read=False
            )
            
            return notification
            
        except Exception as e:
            # Log the error (you might want to use proper logging here)
            print(f"Error sending booking request notification: {str(e)}")
            return None
    
    @staticmethod
    def send_rental_status_update_notification(rental, old_status, new_status, updated_by):
        """
        Send notification when rental status changes
        
        Args:
            rental: SelfDriveRental instance
            old_status: Previous status
            new_status: New status
            updated_by: User who made the change
        """
        try:
            # Determine who should receive the notification
            if updated_by == rental.renter:
                # If renter updated, notify owner
                receiver = rental.car.owner
                sender = rental.renter
            else:
                # If owner updated, notify renter
                receiver = rental.renter
                sender = rental.car.owner
            
            # Create status-specific messages
            status_messages = {
                'Confirmed': f"Your booking request for {rental.car.brand} {rental.car.model} has been confirmed",
                'Canceled': f"Your booking request for {rental.car.brand} {rental.car.model} has been canceled",
                'Ongoing': f"Your rental for {rental.car.brand} {rental.car.model} has started",
                'Finished': f"Your rental for {rental.car.brand} {rental.car.model} has been completed",
            }
            
            message = status_messages.get(new_status, f"Rental status changed from {old_status} to {new_status}")
            
            # Create notification data
            notification_data = {
                "rentalId": rental.id,
                "carId": rental.car.id,
                "oldStatus": old_status,
                "newStatus": new_status,
                "updatedBy": updated_by.id,
                "carName": f"{rental.car.brand} {rental.car.model}",
            }
            
            # Create notification
            notification = Notification.objects.create( # type: ignore
                sender=sender,
                receiver=receiver,
                title=f"Rental Status Update - {new_status}",
                message=message,
                notification_type="RENTAL",
                priority="NORMAL",
                data=notification_data,
                is_read=False
            )
            
            return notification
            
        except Exception as e:
            print(f"Error sending status update notification: {str(e)}")
            return None
    
    @staticmethod
    def send_payment_notification(rental, payment_type, amount, status):
        """
        Send payment-related notifications
        
        Args:
            rental: SelfDriveRental instance
            payment_type: Type of payment (deposit, remaining, excess)
            amount: Payment amount
            status: Payment status
        """
        try:
            # Determine receiver based on payment type
            if payment_type in ['deposit', 'remaining']:
                # Notify owner about payment
                receiver = rental.car.owner
                sender = rental.renter
                message = f"Payment of {amount} EGP for {payment_type} has been {status.lower()}"
            else:
                # Notify renter about refund
                receiver = rental.renter
                sender = rental.car.owner
                message = f"Refund of {amount} EGP has been {status.lower()}"
            
            # Create notification data
            notification_data = {
                "rentalId": rental.id,
                "paymentType": payment_type,
                "amount": amount,
                "status": status,
                "carName": f"{rental.car.brand} {rental.car.model}",
            }
            
            # Create notification
            notification = Notification.objects.create( # type: ignore
                sender=sender,
                receiver=receiver,
                title=f"Payment {status}",
                message=message,
                notification_type="PAYMENT",
                priority="HIGH" if status == "Paid" else "NORMAL",
                data=notification_data,
                is_read=False
            )
            
            return notification
            
        except Exception as e:
            print(f"Error sending payment notification: {str(e)}")
            return None 