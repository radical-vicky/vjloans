from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import timedelta
from django.db.models import Sum
import os  # Add this import

class LoanType(models.Model):
    LOAN_CATEGORIES = [
        ('secured', 'Secured Loans'),
        ('unsecured', 'Unsecured Loans'),
        ('mobile', 'Mobile Loans'),
    ]
    
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=LOAN_CATEGORIES)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, default=1000)
    max_term = models.PositiveIntegerField(help_text="Maximum term in months")
    min_term = models.PositiveIntegerField(default=1)
    description = models.TextField()
    requirements = models.TextField(help_text="Loan requirements")
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"
class BorrowerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    id_number = models.CharField(max_length=20, unique=True)
    phone_number = models.CharField(max_length=15)
    date_of_birth = models.DateField()
    profile_picture = models.ImageField(
        upload_to='profile_pictures/%Y/%m/%d/',
        null=True,
        blank=True,
        default='profile_pictures/default.png'
    )
    employment_status = models.CharField(max_length=20, choices=[
        ('employed', 'Employed'),
        ('self_employed', 'Self-Employed'),
        ('unemployed', 'Unemployed'),
        ('student', 'Student'),
    ])
    monthly_income = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    employer_name = models.CharField(max_length=100, null=True, blank=True)
    credit_score = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.id_number}"
    
    @property
    def has_profile_picture(self):
        return bool(self.profile_picture) and self.profile_picture.name != 'profile_pictures/default.png'
    
class LoanApplication(models.Model):
    APPLICATION_STATUS = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('under_review', 'Under Review'),
        ('more_info', 'More Information Needed'),
    ]
    
    applicant = models.ForeignKey(User, on_delete=models.CASCADE)
    loan_type = models.ForeignKey(LoanType, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(1000)])
    term_months = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(360)])
    purpose = models.TextField()
    status = models.CharField(max_length=20, choices=APPLICATION_STATUS, default='pending')
    application_date = models.DateTimeField(auto_now_add=True)
    approved_date = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_loans')
    rejection_reason = models.TextField(blank=True)
    
    # Calculated fields
    monthly_installment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_repayment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    class Meta:
        ordering = ['-application_date']
    
    def save(self, *args, **kwargs):
        # Calculate repayment amounts when loan is approved
        if self.status == 'approved' and not self.monthly_installment:
            self.calculate_repayment()
        super().save(*args, **kwargs)
        if self.status == 'approved':
            self.create_payment_schedule()
    
    def calculate_repayment(self):
        """Calculate monthly installment and total repayment"""
        if self.loan_type and self.amount and self.term_months:
            monthly_rate = float(self.loan_type.interest_rate) / 100 / 12
            principal = float(self.amount)
            term = self.term_months
            
            # Monthly installment formula: P * r * (1+r)^n / ((1+r)^n - 1)
            if monthly_rate > 0:
                monthly_installment = (principal * monthly_rate * (1 + monthly_rate) ** term) / ((1 + monthly_rate) ** term - 1)
            else:
                monthly_installment = principal / term
                
            self.monthly_installment = round(monthly_installment, 2)
            self.total_repayment = round(monthly_installment * term, 2)
    
    def create_payment_schedule(self):
        """Create payment schedule when loan is approved"""
        # Clear existing payments
        self.payments.all().delete()
        
        # Create monthly payments
        for i in range(self.term_months):
            due_date = timezone.now().date() + timedelta(days=30 * (i + 1))
            LoanPayment.objects.create(
                loan_application=self,
                amount=self.monthly_installment,
                due_date=due_date,
                installment_number=i + 1,
                status='pending'
            )
    
    @property
    def total_paid(self):
        """Calculate total amount paid so far"""
        result = self.payments.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total']
        return result or 0
    
    @property
    def remaining_balance(self):
        """Calculate remaining balance"""
        if self.total_repayment:
            return float(self.total_repayment) - float(self.total_paid)
        return 0
    
    @property
    def next_payment_due(self):
        """Get next due payment"""
        return self.payments.filter(status__in=['pending', 'overdue']).order_by('due_date').first()
    
    def __str__(self):
        return f"{self.applicant.username} - {self.loan_type.name} - {self.amount}"

class LoanDocument(models.Model):
    loan_application = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50, choices=[
        ('id_front', 'National ID Front'),
        ('id_back', 'National ID Back'),
        ('passport', 'Passport Photo'),
        ('payslip', 'Payslip'),
        ('bank_statement', 'Bank Statement'),
        ('business_registration', 'Business Registration'),
        ('other', 'Other'),
    ])
    document_file = models.FileField(upload_to='loan_documents/%Y/%m/%d/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.loan_application} - {self.get_document_type_display()}"

class LoanPayment(models.Model):
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('overdue', 'Overdue'),
    ]
    
    PAYMENT_METHODS = [
        ('mpesa', 'M-Pesa'),
        ('bank', 'Bank Transfer'),
        ('cash', 'Cash Deposit'),
    ]
    
    loan_application = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, blank=True)
    mpesa_number = models.CharField(max_length=15, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)
    is_installment = models.BooleanField(default=True)
    installment_number = models.PositiveIntegerField(default=1)
    
    class Meta:
        ordering = ['due_date']
    
    def __str__(self):
        return f"Payment - {self.loan_application} - KSh {self.amount}"
    
    @property
    def is_overdue(self):
        return self.due_date < timezone.now().date() and self.status in ['pending', 'failed']

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    notification_type = models.CharField(max_length=20, choices=[
        ('application_update', 'Application Update'),
        ('payment_reminder', 'Payment Reminder'),
        ('system', 'System Notification'),
        ('withdrawal', 'Withdrawal Update'),
        ('payment', 'Payment Update'),
    ])
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.title}"

class LoanWithdrawal(models.Model):
    WITHDRAWAL_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    loan_application = models.OneToOneField(LoanApplication, on_delete=models.CASCADE)
    mpesa_number = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=WITHDRAWAL_STATUS, default='pending')
    withdrawal_date = models.DateTimeField(auto_now_add=True)
    processed_date = models.DateTimeField(null=True, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)
    failure_reason = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-withdrawal_date']
    
    def __str__(self):
        return f"Withdrawal - {self.loan_application} - {self.mpesa_number}"