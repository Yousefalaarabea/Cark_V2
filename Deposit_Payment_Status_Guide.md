# Rental Status Guide - Deposit Payment

## Rental Status Flow

### 1. **PendingOwnerConfirmation**
- **Description**: Rental created, waiting for owner to confirm
- **Can Pay Deposit**: ❌ **NO** - Owner must confirm first
- **Error Message**: "يجب أن يؤكد مالك السيارة الحجز أولاً قبل دفع العربون"

### 2. **DepositRequired** 
- **Description**: Owner confirmed booking, deposit payment required
- **Can Pay Deposit**: ✅ **YES** - This is the correct status for deposit payment
- **Next Status**: Will become `Confirmed` after successful payment

### 3. **Confirmed**
- **Description**: Deposit paid successfully, rental is confirmed
- **Can Pay Deposit**: ❌ **NO** - Deposit already paid
- **Error Message**: "تم دفع العربون بالفعل"
- **Next Actions**: 
  - Driver can confirm arrival (`owner_confirm_arrival`)
  - Renter can announce they are on the way (`renter_on_way`)

### 4. **Ongoing**
- **Description**: Trip has started
- **Can Pay Deposit**: ❌ **NO** - Trip already started

### 5. **Finished**
- **Description**: Trip completed
- **Can Pay Deposit**: ❌ **NO** - Trip finished

### 6. **Canceled**
- **Description**: Rental was canceled
- **Can Pay Deposit**: ❌ **NO** - Rental canceled

## Common Error Scenarios

### Scenario 1: Trying to pay deposit when status is "Confirmed"
```json
{
    "error_code": "DEPOSIT_ALREADY_PAID",
    "error_message": "تم دفع العربون بالفعل. الحالة الحالية: Confirmed"
}
```
**Solution**: Deposit is already paid. You can proceed to next steps.

### Scenario 2: Trying to pay deposit when status is "PendingOwnerConfirmation"
```json
{
    "error_code": "OWNER_CONFIRMATION_REQUIRED",
    "error_message": "يجب أن يؤكد مالك السيارة الحجز أولاً قبل دفع العربون. الحالة الحالية: PendingOwnerConfirmation"
}
```
**Solution**: Wait for owner to confirm the booking first.

### Scenario 3: Trying to pay deposit when status is "Ongoing"
```json
{
    "error_code": "INVALID_STATUS",
    "error_message": "لا يمكن دفع العربون في هذه الحالة. الحالة الحالية: Ongoing"
}
```
**Solution**: Trip has already started, deposit payment is not needed.

## Complete Workflow

1. **Create Rental** → `PendingOwnerConfirmation`
2. **Owner Confirms** → `DepositRequired` ✅ **PAY DEPOSIT HERE**
3. **Renter Pays Deposit** → `Confirmed`
4. **Driver Confirms Arrival** → `owner_arrival_confirmed = True`
5. **Renter Announces On Way** → `renter_on_way_announced = True`
6. **Driver Starts Trip** → `Ongoing`
7. **Trip Ends** → `Finished`

## API Endpoints for Deposit Payment

### 1. Saved Card Payment
```
POST /api/rentals/{id}/deposit_payment/
```
**Required Status**: `DepositRequired`

### 2. New Card Payment
```
POST /api/rentals/{id}/new_card_deposit_payment/
```
**Required Status**: `DepositRequired`

## Testing Checklist

- [ ] Create rental → Status should be `PendingOwnerConfirmation`
- [ ] Try to pay deposit → Should get "OWNER_CONFIRMATION_REQUIRED" error
- [ ] Owner confirms booking → Status should be `DepositRequired`
- [ ] Pay deposit → Should succeed and status becomes `Confirmed`
- [ ] Try to pay deposit again → Should get "DEPOSIT_ALREADY_PAID" error
- [ ] Continue with next steps (driver arrival, renter on way, etc.) 