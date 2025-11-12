from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.utils import timezone
from .models import LoanApplication, LoanType, BorrowerProfile, Notification, LoanDocument, LoanWithdrawal, LoanPayment
from .forms import LoanApplicationForm, BorrowerProfileForm, UserUpdateForm, LoanDocumentForm, LoanWithdrawalForm, LoanPaymentForm

def create_notification(user, title, message, notification_type='system'):
    """Helper function to create notifications"""
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type
    )

def home(request):
    """Public home page"""
    # Get active loan types from database
    loan_types = LoanType.objects.filter(is_active=True)
    
    context = {
        'loan_types': loan_types,
    }
    return render(request, 'dashboard/home.html', context)

@login_required
def dashboard(request):
    """User dashboard"""
    # Get user's loan applications
    user_loans = LoanApplication.objects.filter(applicant=request.user)
    recent_loans = user_loans.order_by('-application_date')[:5]
    
    # Get unread notifications
    unread_notifications = Notification.objects.filter(user=request.user, is_read=False)[:5]
    
    # Calculate stats
    total_applications = user_loans.count()
    approved_loans = user_loans.filter(status='approved').count()
    pending_applications = user_loans.filter(status__in=['pending', 'under_review', 'more_info']).count()
    
    # Calculate payment stats
    user_payments = LoanPayment.objects.filter(loan_application__applicant=request.user)
    total_paid = user_payments.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
    overdue_payments = user_payments.filter(
        due_date__lt=timezone.now().date(),
        status__in=['pending', 'failed']
    ).count()
    
    context = {
        'recent_loans': recent_loans,
        'unread_notifications': unread_notifications,
        'total_applications': total_applications,
        'approved_loans': approved_loans,
        'pending_applications': pending_applications,
        'total_paid': total_paid,
        'overdue_payments': overdue_payments,
    }
    return render(request, 'dashboard/dashboard.html', context)

@login_required
def loan_list(request):
    loan_types = LoanType.objects.filter(is_active=True)
    
    # Filter by category if provided
    category = request.GET.get('category')
    if category:
        loan_types = loan_types.filter(category=category)
    
    context = {
        'loan_types': loan_types,
        'categories': LoanType.LOAN_CATEGORIES,
    }
    return render(request, 'dashboard/loan_list.html', context)

@login_required
def loan_apply(request, loan_type_id):
    loan_type = get_object_or_404(LoanType, id=loan_type_id, is_active=True)
    
    # Check if user has a complete profile
    try:
        profile = request.user.borrowerprofile
    except BorrowerProfile.DoesNotExist:
        messages.warning(request, 'Please complete your profile before applying for a loan.')
        return redirect('profile_update')
    
    if request.method == 'POST':
        form = LoanApplicationForm(request.POST)
        if form.is_valid():
            loan_application = form.save(commit=False)
            loan_application.applicant = request.user
            loan_application.loan_type = loan_type
            loan_application.save()
            
            # Create notification for application submission
            create_notification(
                user=request.user,
                title='Loan Application Submitted',
                message=f'Your {loan_type.name} application for KSh {loan_application.amount:,.2f} has been submitted successfully and is under review.',
                notification_type='application_update'
            )
            
            # Create welcome notification for first-time applicants
            user_loan_count = LoanApplication.objects.filter(applicant=request.user).count()
            if user_loan_count == 1:
                create_notification(
                    user=request.user,
                    title='Welcome to QuickLoan!',
                    message='Thank you for your first loan application with us. We will review your application and get back to you soon.',
                    notification_type='system'
                )
            
            messages.success(request, 'Loan application submitted successfully!')
            return redirect('loan_detail', application_id=loan_application.id)
    else:
        form = LoanApplicationForm(initial={'loan_type': loan_type})
    
    context = {
        'form': form,
        'loan_type': loan_type,
    }
    return render(request, 'dashboard/loan_apply.html', context)

@login_required
def loan_detail(request, application_id):
    try:
        # First, check if the loan application exists at all
        loan_application = LoanApplication.objects.get(id=application_id)
        
        # Then check if the current user is the applicant
        if loan_application.applicant != request.user:
            messages.error(request, 'You do not have permission to view this loan application.')
            return redirect('application_history')
            
    except LoanApplication.DoesNotExist:
        messages.error(request, f'Loan application with ID {application_id} does not exist.')
        return redirect('application_history')
    
    # Handle document upload
    if request.method == 'POST' and 'upload_document' in request.POST:
        document_form = LoanDocumentForm(request.POST, request.FILES)
        if document_form.is_valid():
            document = document_form.save(commit=False)
            document.loan_application = loan_application
            document.save()
            
            # Create notification for document upload
            create_notification(
                user=request.user,
                title='Document Uploaded',
                message=f'Your {document.get_document_type_display()} has been uploaded successfully for your {loan_application.loan_type.name} application.',
                notification_type='application_update'
            )
            
            messages.success(request, 'Document uploaded successfully!')
            return redirect('loan_detail', application_id=application_id)
    else:
        document_form = LoanDocumentForm()

    # Check if withdrawal exists
    try:
        withdrawal = loan_application.loanwithdrawal
    except LoanWithdrawal.DoesNotExist:
        withdrawal = None
    
    # Document types for checklist
    document_types = [
        ('id_front', 'National ID Front'),
        ('id_back', 'National ID Back'), 
        ('passport', 'Passport Photo'),
    ]
    
    # Get uploaded document types
    uploaded_doc_types = [doc.document_type for doc in loan_application.documents.all()]
    
    # Count completed payments for the template
    completed_payments_count = loan_application.payments.filter(status='completed').count()
    
    # Check for overdue payments and create notifications
    overdue_payments = loan_application.payments.filter(
        due_date__lt=timezone.now().date(),
        status__in=['pending', 'failed']
    )
    
    if overdue_payments.exists() and loan_application.status == 'approved':
        # Create overdue payment notification (only once per day)
        today = timezone.now().date()
        recent_overdue_notification = Notification.objects.filter(
            user=request.user,
            title__contains='Payment Overdue',
            created_at__date=today
        ).exists()
        
        if not recent_overdue_notification:
            create_notification(
                user=request.user,
                title='Payment Overdue',
                message=f'You have {overdue_payments.count()} overdue payment(s) for your {loan_application.loan_type.name}. Please make payment to avoid penalties.',
                notification_type='payment_reminder'
            )
    
    context = {
        'loan_application': loan_application,
        'document_form': document_form,
        'documents': loan_application.documents.all(),
        'withdrawal': withdrawal,
        'total_paid': loan_application.total_paid,
        'remaining_balance': loan_application.remaining_balance,
        'next_payment': loan_application.next_payment_due,
        'document_types': document_types,
        'uploaded_doc_types': uploaded_doc_types,
        'completed_payments_count': completed_payments_count,  # Added for template
    }
    return render(request, 'dashboard/loan_detail.html', context)

@login_required
def loan_withdraw(request, application_id):
    loan_application = get_object_or_404(
        LoanApplication, 
        id=application_id, 
        applicant=request.user,
        status='approved'
    )
    
    # Check if already withdrawn
    if hasattr(loan_application, 'loanwithdrawal'):
        messages.info(request, 'Funds have already been withdrawn for this loan.')
        return redirect('loan_detail', application_id=application_id)
    
    if request.method == 'POST':
        form = LoanWithdrawalForm(request.POST)
        if form.is_valid():
            withdrawal = form.save(commit=False)
            withdrawal.loan_application = loan_application
            withdrawal.amount = loan_application.amount
            withdrawal.status = 'processing'
            withdrawal.save()
            
            # Simulate M-Pesa processing
            withdrawal.status = 'completed'
            withdrawal.transaction_id = f"MP{timezone.now().strftime('%Y%m%d%H%M%S')}"
            withdrawal.processed_date = timezone.now()
            withdrawal.save()
            
            # Create withdrawal notification
            create_notification(
                user=request.user,
                title='Loan Disbursement Successful! 🎉',
                message=f'KSh {withdrawal.amount:,.2f} has been sent to your M-Pesa number {withdrawal.mpesa_number}. Transaction ID: {withdrawal.transaction_id}. Funds should arrive within 5 minutes.',
                notification_type='withdrawal'
            )
            
            # Create payment reminder notification
            next_payment = loan_application.payments.first()
            if next_payment:
                create_notification(
                    user=request.user,
                    title='Payment Schedule Created',
                    message=f'Your payment schedule has been created. First payment of KSh {loan_application.monthly_installment:,.2f} is due on {next_payment.due_date.strftime("%B %d, %Y")}.',
                    notification_type='payment_reminder'
                )
            
            messages.success(request, f'KSh {withdrawal.amount:,.2f} has been successfully sent to your M-Pesa account!')
            return redirect('loan_detail', application_id=application_id)
    else:
        form = LoanWithdrawalForm()
    
    context = {
        'form': form,
        'loan_application': loan_application,
    }
    return render(request, 'dashboard/loan_withdraw.html', context)

@login_required
def make_payment(request, application_id):
    loan_application = get_object_or_404(
        LoanApplication, 
        id=application_id, 
        applicant=request.user
    )
    
    # Get pending payments
    pending_payments = loan_application.payments.filter(
        status__in=['pending', 'overdue']
    ).order_by('due_date')
    
    if request.method == 'POST':
        form = LoanPaymentForm(request.POST, loan_application=loan_application)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.loan_application = loan_application
            payment.status = 'processing'
            payment.payment_date = timezone.now()
            
            # Find which installment this payment is for and set due_date
            next_payment = pending_payments.first()
            if next_payment:
                payment.installment_number = next_payment.installment_number
                payment.due_date = next_payment.due_date
            else:
                payment.due_date = timezone.now().date()
                payment.installment_number = 1
            
            payment.save()
            
            # Simulate payment processing
            payment.status = 'completed'
            payment.transaction_id = f"PY{timezone.now().strftime('%Y%m%d%H%M%S')}"
            payment.save()
            
            # Update the original payment record if it exists
            if next_payment:
                next_payment.status = 'completed'
                next_payment.transaction_id = payment.transaction_id
                next_payment.payment_date = timezone.now()
                next_payment.save()
            
            # Create payment notification
            create_notification(
                user=request.user,
                title='Payment Successful! ✅',
                message=f'Payment of KSh {payment.amount:,.2f} for your {loan_application.loan_type.name} has been processed successfully. Transaction ID: {payment.transaction_id}.',
                notification_type='payment'
            )
            
            # Check if loan is fully paid
            if loan_application.remaining_balance <= 0:
                create_notification(
                    user=request.user,
                    title='Loan Fully Paid! 🎊',
                    message=f'Congratulations! You have successfully completed all payments for your {loan_application.loan_type.name}. Thank you for being a valued customer.',
                    notification_type='system'
                )
            
            messages.success(request, f'Payment of KSh {payment.amount:,.2f} processed successfully!')
            return redirect('loan_detail', application_id=application_id)
    else:
        form = LoanPaymentForm(loan_application=loan_application)
    
    # Calculate total due amount safely
    total_due = 0
    for payment in pending_payments:
        total_due += float(payment.amount)
    
    context = {
        'form': form,
        'loan_application': loan_application,
        'pending_payments': pending_payments,
        'total_due': total_due,
    }
    return render(request, 'dashboard/make_payment.html', context)

@login_required
def payment_history(request, application_id):
    loan_application = get_object_or_404(
        LoanApplication, 
        id=application_id, 
        applicant=request.user
    )
    
    payments = loan_application.payments.all().order_by('-due_date')
    total_paid = loan_application.total_paid
    remaining_balance = loan_application.remaining_balance
    
    context = {
        'loan_application': loan_application,
        'payments': payments,
        'total_paid': total_paid,
        'remaining_balance': remaining_balance,
    }
    return render(request, 'dashboard/payment_history.html', context)



@login_required
def profile(request):
    try:
        profile = request.user.borrowerprofile
    except BorrowerProfile.DoesNotExist:
        return redirect('profile_update')
    
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = BorrowerProfileForm(
            request.POST, 
            request.FILES,  # Add this to handle file uploads
            instance=profile
        )
        
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            
            # Create profile update notification
            create_notification(
                user=request.user,
                title='Profile Updated',
                message='Your profile information has been updated successfully.',
                notification_type='system'
            )
            
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = BorrowerProfileForm(instance=profile)
    
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
    }
    return render(request, 'dashboard/profile.html', context)

@login_required
def profile_update(request):
    try:
        profile = request.user.borrowerprofile
        is_update = True
    except BorrowerProfile.DoesNotExist:
        profile = None
        is_update = False
    
    if request.method == 'POST':
        if is_update:
            form = BorrowerProfileForm(request.POST, request.FILES, instance=profile)  # Add request.FILES
        else:
            form = BorrowerProfileForm(request.POST, request.FILES)  # Add request.FILES
        
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            
            # Create profile completion notification
            if not is_update:
                create_notification(
                    user=request.user,
                    title='Profile Completed!',
                    message='Your borrower profile has been completed successfully. You can now apply for loans.',
                    notification_type='system'
                )
            else:
                create_notification(
                    user=request.user,
                    title='Profile Updated',
                    message='Your profile information has been updated successfully.',
                    notification_type='system'
                )
            
            messages.success(request, 'Profile completed successfully!')
            return redirect('dashboard')
    else:
        form = BorrowerProfileForm(instance=profile)
    
    context = {
        'form': form,
        'is_update': is_update,
    }
    return render(request, 'dashboard/profile_update.html', context)

@login_required
def profile_update(request):
    try:
        profile = request.user.borrowerprofile
        is_update = True
    except BorrowerProfile.DoesNotExist:
        profile = None
        is_update = False
    
    if request.method == 'POST':
        if is_update:
            form = BorrowerProfileForm(request.POST, instance=profile)
        else:
            form = BorrowerProfileForm(request.POST)
        
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            
            # Create profile completion notification
            if not is_update:
                create_notification(
                    user=request.user,
                    title='Profile Completed!',
                    message='Your borrower profile has been completed successfully. You can now apply for loans.',
                    notification_type='system'
                )
            else:
                create_notification(
                    user=request.user,
                    title='Profile Updated',
                    message='Your profile information has been updated successfully.',
                    notification_type='system'
                )
            
            messages.success(request, 'Profile completed successfully!')
            return redirect('dashboard')
    else:
        form = BorrowerProfileForm(instance=profile)
    
    context = {
        'form': form,
        'is_update': is_update,
    }
    return render(request, 'dashboard/profile_update.html', context)

@login_required
def application_history(request):
    applications = LoanApplication.objects.filter(applicant=request.user).order_by('-application_date')
    
    # Check for application status updates and create notifications
    for application in applications:
        if application.status == 'approved':
            # Check if we haven't notified about this approval yet
            recent_approval_notification = Notification.objects.filter(
                user=request.user,
                title__contains='Application Approved',
                message__contains=f'{application.loan_type.name}'
            ).exists()
            
            if not recent_approval_notification:
                create_notification(
                    user=request.user,
                    title='Application Approved! 🎉',
                    message=f'Great news! Your {application.loan_type.name} application for KSh {application.amount:,.2f} has been approved. You can now withdraw the funds.',
                    notification_type='application_update'
                )
    
    # Pagination
    paginator = Paginator(applications, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
    }
    return render(request, 'dashboard/application_history.html', context)

@login_required
def notifications(request):
    notifications_list = Notification.objects.filter(user=request.user).order_by('-created_at')
    
    # Handle mark as read action
    if request.method == 'POST':
        if 'mark_read' in request.POST:
            notification_id = request.POST.get('notification_id')
            if notification_id:
                notification = get_object_or_404(Notification, id=notification_id, user=request.user)
                notification.is_read = True
                notification.save()
                messages.success(request, 'Notification marked as read.')
        
        elif 'mark_all_read' in request.POST:
            updated_count = notifications_list.filter(is_read=False).update(is_read=True)
            messages.success(request, f'{updated_count} notifications marked as read.')
        
        return redirect('notifications')
    
    # Pagination
    paginator = Paginator(notifications_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'notifications': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'dashboard/notifications.html', context)

# Admin function to create system-wide notifications (optional)
@login_required
def create_system_notification(request):
    """Admin function to create system-wide notifications"""
    if not request.user.is_superuser:
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('dashboard')
        
    if request.method == 'POST':
        from django.contrib.auth.models import User
        title = request.POST.get('title')
        message = request.POST.get('message')
        
        if title and message:
            users = User.objects.filter(is_active=True)
            for user in users:
                create_notification(
                    user=user,
                    title=title,
                    message=message,
                    notification_type='system'
                )
            
            messages.success(request, f'System notification sent to {users.count()} users.')
            return redirect('dashboard')
        else:
            messages.error(request, 'Title and message are required.')
    
    return render(request, 'dashboard/create_system_notification.html')