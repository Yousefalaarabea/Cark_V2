# Renter On The Way API Documentation

## Overview
This API allows renters to announce that they are on their way to meet the driver at the pickup location.

## Endpoint
```
POST /api/rentals/{rental_id}/renter_on_way/
```

## Authentication
- Requires authentication
- Only the renter of the rental can use this endpoint

## Request Parameters
- **rental_id** (path parameter): The ID of the rental

## Request Body
No body required - this is a simple POST request.

## Response

### Success Response (200 OK)
```json
{
    "status": "Renter on the way announced.",
    "message": "Driver has been notified that you are on the way.",
    "announced_at": "2024-01-15T10:30:00Z",
    "pickup_address": "123 Main Street, Cairo"
}
```

### Error Responses

#### 403 Forbidden - Not Renter
```json
{
    "error_code": "NOT_RENTER",
    "error_message": "Only the renter can announce they are on the way."
}
```

#### 400 Bad Request - Invalid Status
```json
{
    "error_code": "INVALID_STATUS",
    "error_message": "Can only announce arrival when rental is confirmed. Current status: PendingOwnerConfirmation"
}
```

#### 400 Bad Request - Driver Not Arrived
```json
{
    "error_code": "DRIVER_NOT_ARRIVED",
    "error_message": "Driver must confirm arrival at pickup location before you can announce you are on the way.",
    "driver_arrival_status": "pending"
}
```

#### 400 Bad Request - Already Announced
```json
{
    "error_code": "ALREADY_ANNOUNCED",
    "error_message": "You have already announced that you are on the way.",
    "announced_at": "2024-01-15T10:25:00Z"
}
```

## Business Logic

### Workflow Order
1. **Rental Created** → Status: `PendingOwnerConfirmation`
2. **Owner Confirms Booking** → Status: `DepositRequired`
3. **Renter Pays Deposit** → Status: `Confirmed`
4. **Driver Confirms Arrival** → `owner_arrival_confirmed = True` ✅
5. **Renter Announces On The Way** → `renter_on_way_announced = True` ✅
6. **Driver Starts Trip** → Status: `Ongoing`

### When Can This Be Used?
- Rental status must be either `Confirmed` or `DepositRequired`
- **Driver must have confirmed arrival at pickup location first** (`owner_arrival_confirmed = True`)
- Only the renter can use this endpoint
- Can only be used once per rental

### What Happens When Used?
1. **Status Update**: Sets `renter_on_way_announced = True` and records the timestamp
2. **Log Entry**: Creates a log entry in `RentalLog` with event "Renter announced they are on the way"
3. **Notification**: Sends a notification to the car owner (driver) with title "Renter On The Way"
4. **Response**: Returns confirmation with timestamp and pickup address

### Notification Details
- **Receiver**: Car owner (driver)
- **Title**: "Renter On The Way"
- **Message**: "Your renter is on the way to {pickup_address}. Please be ready."
- **Type**: "RENTAL"
- **Data**: Contains rental_id and pickup_address

## Usage Example

### cURL
```bash
curl -X POST \
  http://localhost:8000/api/rentals/123/renter_on_way/ \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json'
```

### JavaScript/Fetch
```javascript
const response = await fetch('/api/rentals/123/renter_on_way/', {
    method: 'POST',
    headers: {
        'Authorization': 'Bearer YOUR_TOKEN',
        'Content-Type': 'application/json'
    }
});

const data = await response.json();
console.log(data);
```

## Related Endpoints
- `POST /api/rentals/{id}/owner_confirm_arrival/` - Driver confirms arrival at pickup (**Required before renter can announce they are on the way**)
- `POST /api/rentals/{id}/start_trip/` - Driver starts the trip

## Database Changes
The following fields were added to the `Rental` model:
- `renter_on_way_announced` (Boolean): Whether renter announced they are on the way
- `renter_on_way_announced_at` (DateTime): When renter announced they are on the way

## Migration
Migration file: `rentals/migrations/0008_rental_renter_on_way_announced_and_more.py` 