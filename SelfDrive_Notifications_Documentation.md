# Self-Drive Rental Notifications System

## Overview
This document describes the notification system implemented for self-drive rentals in the CARK backend. The system automatically sends notifications to car owners when new booking requests are made, and to both parties when rental status changes or payments are processed.

## Features Implemented

### 1. Booking Request Notifications
When a new self-drive rental is created, the system automatically sends a notification to the car owner with all relevant booking details.

**Notification Structure:**
```json
{
  "title": "New Booking Request",
  "message": "John Doe has requested to rent your Toyota Camry",
  "type": "RENTAL",
  "priority": "HIGH",
  "isRead": false,
  "data": {
    "renterId": 123,
    "carId": 456,
    "status": "PendingOwnerConfirmation",
    "rentalId": 789,
    "startDate": "2024-01-01T10:00:00Z",
    "endDate": "2024-01-03T10:00:00Z",
    "pickupAddress": "Cairo, Egypt",
    "dropoffAddress": "Alexandria, Egypt",
    "renterName": "John Doe",
    "carName": "Toyota Camry",
    "dailyPrice": 200.0,
    "totalDays": 3,
    "totalAmount": 600.0,
    "depositAmount": 90.0
  }
}
```

### 2. Status Update Notifications
When rental status changes, notifications are sent to the appropriate party:

- **Owner confirms rental**: Notification sent to renter
- **Renter pays deposit**: Notification sent to owner
- **Rental starts**: Notification sent to both parties
- **Rental finishes**: Notification sent to both parties
- **Rental canceled**: Notification sent to both parties

### 3. Payment Notifications
Payment-related notifications are sent when:
- Deposit is paid
- Remaining amount is paid
- Excess charges are paid
- Refunds are processed

## Implementation Details

### Files Created/Modified

1. **`notifications/services.py`** - New service class for handling notifications
2. **`selfdrive_rentals/signals.py`** - New signals file for automatic notifications
3. **`selfdrive_rentals/apps.py`** - Modified to register signals
4. **`selfdrive_rentals/views.py`** - Modified to include notification calls
5. **`notifications/views.py`** - Added test endpoint
6. **`notifications/tests.py`** - Added comprehensive tests

### Key Components

#### NotificationService Class
Located in `notifications/services.py`, this class provides static methods for:
- `send_booking_request_notification(rental)` - Sends booking request to owner
- `send_rental_status_update_notification(rental, old_status, new_status, updated_by)` - Sends status updates
- `send_payment_notification(rental, payment_type, amount, status)` - Sends payment notifications

#### Automatic Triggers
The system uses Django signals to automatically trigger notifications:
- **Post-save signal on SelfDriveRental**: Triggers booking request notification
- **Post-save signal on SelfDriveRentalStatusHistory**: Triggers status update notifications

#### Manual Triggers
Notifications are also manually triggered in key view methods:
- `confirm_by_owner()` - When owner confirms rental
- `deposit_payment()` - When deposit is paid

## API Endpoints

### Existing Notification Endpoints
- `GET /api/notifications/` - List all notifications for current user
- `GET /api/notifications/unread/` - List unread notifications
- `GET /api/notifications/count/` - Get notification counts
- `POST /api/notifications/{id}/mark_as_read/` - Mark notification as read
- `POST /api/notifications/mark_all_as_read/` - Mark all notifications as read

### Test Endpoint
- `POST /api/notifications/test_booking_notification/` - Create test notification

## Usage Examples

### Frontend Integration
The frontend can use the notification data to display relevant information:

```javascript
// Example: Display booking request notification
const notification = {
  title: "New Booking Request",
  message: "John Doe has requested to rent your Toyota Camry",
  data: {
    renterId: 123,
    carId: 456,
    rentalId: 789,
    renterName: "John Doe",
    carName: "Toyota Camry",
    startDate: "2024-01-01T10:00:00Z",
    endDate: "2024-01-03T10:00:00Z",
    totalAmount: 600.0,
    depositAmount: 90.0
  }
};

// Use data to populate UI components
const bookingCard = {
  renterName: notification.data.renterName,
  carName: notification.data.carName,
  rentalPeriod: `${notification.data.startDate} - ${notification.data.endDate}`,
  totalAmount: notification.data.totalAmount,
  depositAmount: notification.data.depositAmount
};
```

### Notification Actions
Based on notification type and data, the frontend can provide appropriate actions:

```javascript
// For booking requests
if (notification.notification_type === 'RENTAL' && notification.data.status === 'PendingOwnerConfirmation') {
  // Show accept/reject buttons
  showActionButtons({
    accept: () => confirmRental(notification.data.rentalId),
    reject: () => rejectRental(notification.data.rentalId)
  });
}

// For payment notifications
if (notification.notification_type === 'PAYMENT') {
  // Show payment details
  showPaymentDetails({
    amount: notification.data.amount,
    type: notification.data.paymentType,
    status: notification.data.status
  });
}
```

## Testing

### Running Tests
```bash
python manage.py test notifications.tests.NotificationServiceTestCase
```

### Test Coverage
The test suite covers:
- Booking request notification creation
- Status update notification creation
- Payment notification creation
- Notification data validation
- Sender/receiver assignment

## Future Enhancements

1. **Push Notifications**: Integrate with Firebase Cloud Messaging for real-time notifications
2. **Email Notifications**: Send email notifications for important events
3. **SMS Notifications**: Send SMS for critical updates
4. **Notification Templates**: Create customizable notification templates
5. **Notification Preferences**: Allow users to configure notification preferences
6. **Bulk Notifications**: Support for sending notifications to multiple users

## Error Handling

The notification system includes comprehensive error handling:
- Graceful failure if notification creation fails
- Logging of notification errors
- Fallback mechanisms for missing data
- Validation of required fields before notification creation

## Performance Considerations

- Notifications are created asynchronously to avoid blocking the main request
- Database queries are optimized to minimize impact
- Notification data is cached where appropriate
- Bulk operations are used for multiple notifications 