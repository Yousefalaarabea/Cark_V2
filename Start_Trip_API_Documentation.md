# Start Trip API Documentation

## Overview
This API allows car owners (drivers) to start a rental trip with automatic payment processing using the selected saved card.

## Endpoint
```
POST /api/rentals/{rental_id}/start_trip/
```

## Authentication
- Requires authentication
- Only the car owner can use this endpoint

## Request Parameters
- **rental_id** (path parameter): The ID of the rental

## Request Body
No body required - this is a simple POST request.

## Prerequisites
Before starting a trip, the following conditions must be met:

1. **Rental Status**: Must be `Confirmed` (deposit paid)
2. **Owner Arrival**: Owner must have confirmed arrival at pickup location
3. **Renter On Way**: Renter should have announced they are on the way (recommended)
4. **Selected Card**: For visa/wallet payments, a selected card must be available
5. **Breakdown**: Rental costs must be calculated

## Response

### Success Response (200 OK)
```json
{
    "status": "Trip started successfully.",
    "trip_details": {
        "rental_id": 14,
        "car_info": {
            "brand": "Toyota",
            "model": "Camry",
            "plate_number": "ABC-123",
            "color": "White"
        },
        "route_info": {
            "pickup_address": "123 Main Street, Cairo",
            "dropoff_address": "456 Business District, Cairo",
            "start_date": "2024-01-15",
            "end_date": "2024-01-15"
        },
        "participants": {
            "driver": {
                "id": 1,
                "name": "Ahmed Mohamed",
                "phone": "+201234567890"
            },
            "renter": {
                "id": 2,
                "name": "Sarah Ali",
                "phone": "+201098765432"
            }
        }
    },
    "payment_details": {
        "method": "visa",
        "status": "Paid",
        "remaining_amount": 500.00,
        "transaction_id": "txn_123456789",
        "card_info": {
            "brand": "Visa",
            "last_four": "1234"
        }
    },
    "trip_status": {
        "old_status": "Confirmed",
        "new_status": "Ongoing",
        "started_at": "2024-01-15T10:30:00Z",
        "owner_arrival_confirmed": true,
        "renter_on_way_announced": true
    },
    "message": "Remaining amount 500.00 EGP charged successfully via Visa card.",
    "next_actions": [
        "Use stop_arrival endpoint to confirm arrival at each stop",
        "Use end_waiting endpoint to end waiting at each stop",
        "Use end_trip endpoint when trip is finished"
    ]
}
```

### Error Responses

#### 403 Forbidden - Not Owner
```json
{
    "error_code": "NOT_OWNER",
    "error_message": "Only the car owner can start the trip.",
    "required_role": "car_owner"
}
```

#### 400 Bad Request - Invalid Status
```json
{
    "error_code": "INVALID_STATUS",
    "error_message": "Trip can only be started after deposit is paid and booking is confirmed.",
    "current_status": "PendingOwnerConfirmation",
    "required_status": "Confirmed",
    "next_actions": {
        "PendingOwnerConfirmation": "Wait for owner to confirm booking",
        "DepositRequired": "Renter must pay deposit first",
        "Ongoing": "Trip is already started",
        "Finished": "Trip is already finished",
        "Canceled": "Trip was canceled"
    }
}
```

#### 400 Bad Request - Owner Arrival Required
```json
{
    "error_code": "OWNER_ARRIVAL_REQUIRED",
    "error_message": "Owner must confirm arrival at pickup location before starting the trip.",
    "required_action": "owner_confirm_arrival",
    "pickup_address": "123 Main Street, Cairo",
    "endpoint": "/api/rentals/14/owner_confirm_arrival/"
}
```

#### 400 Bad Request - Renter Not On Way
```json
{
    "error_code": "RENTER_NOT_ON_WAY",
    "error_message": "Renter has not announced they are on the way yet.",
    "warning": "You can still start the trip, but it's recommended to wait for renter confirmation.",
    "can_proceed": true,
    "endpoint": "/api/rentals/14/renter_on_way/"
}
```

#### 400 Bad Request - No Selected Card
```json
{
    "error_code": "NO_SELECTED_CARD",
    "error_message": "No selected card found for automatic payment.",
    "payment_method": "visa",
    "required_action": "Select a card for automatic payments"
}
```

#### 402 Payment Required - Payment Failed
```json
{
    "error_code": "PAYMENT_FAILED",
    "error_message": "Payment for remaining amount failed.",
    "payment_details": {
        "method": "visa",
        "card_brand": "Visa",
        "card_last_four": "1234",
        "amount": 500.00,
        "failure_reason": "Insufficient funds"
    },
    "suggestions": [
        "Check card balance",
        "Verify card is still valid",
        "Try with a different card"
    ]
}
```

## Business Logic

### Payment Processing
1. **Visa/Wallet Payments**: Automatically charges the remaining amount using the selected saved card
2. **Cash Payments**: Marks payment as pending for cash collection at trip end
3. **Real Payment Gateway**: Uses actual payment processing (not dummy)

### Trip Status Flow
1. **Confirmed** → **Ongoing** (after successful payment)
2. **Payment Status**: Updated based on payment method and success
3. **Log Entry**: Creates detailed log entry
4. **Notification**: Sends notification to renter

### Automatic Actions
- Updates rental status to `Ongoing`
- Processes payment using selected card
- Creates detailed log entry
- Sends notification to renter
- Records transaction details

## Usage Example

### cURL
```bash
curl -X POST \
  http://localhost:8000/api/rentals/14/start_trip/ \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json'
```

### JavaScript/Fetch
```javascript
const response = await fetch('/api/rentals/14/start_trip/', {
    method: 'POST',
    headers: {
        'Authorization': 'Bearer YOUR_TOKEN',
        'Content-Type': 'application/json'
    }
});

const data = await response.json();
console.log('Trip started:', data);
```

## Related Endpoints

### Prerequisites
- `POST /api/rentals/{id}/owner_confirm_arrival/` - Driver confirms arrival
- `POST /api/rentals/{id}/renter_on_way/` - Renter announces they are on the way

### Next Steps
- `POST /api/rentals/{id}/stop_arrival/` - Confirm arrival at stops
- `POST /api/rentals/{id}/end_waiting/` - End waiting at stops
- `POST /api/rentals/{id}/end_trip/` - End the trip

## Testing Checklist

- [ ] Create rental and confirm booking
- [ ] Pay deposit (status becomes `Confirmed`)
- [ ] Driver confirms arrival (`owner_confirm_arrival`)
- [ ] Renter announces on the way (`renter_on_way`)
- [ ] Start trip - should succeed with payment processing
- [ ] Verify payment was charged to selected card
- [ ] Check notification was sent to renter
- [ ] Verify rental status changed to `Ongoing`

## Error Handling

### Common Scenarios
1. **No Selected Card**: For visa/wallet rentals without a selected card
2. **Payment Failure**: When card payment fails (insufficient funds, expired card, etc.)
3. **Missing Prerequisites**: When owner hasn't confirmed arrival or renter hasn't announced on the way
4. **Invalid Status**: When rental is not in the correct status for starting trip

### Recovery Actions
- For payment failures: Check card details and try again
- For missing prerequisites: Complete required steps first
- For invalid status: Follow the workflow in the correct order 