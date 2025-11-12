from django.contrib import admin
from .models import LoanType, BorrowerProfile, LoanApplication, LoanDocument, Notification, LoanWithdrawal, LoanPayment

@admin.register(LoanType)
class LoanTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'interest_rate', 'max_amount', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name']

@admin.register(BorrowerProfile)
class BorrowerProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'id_number', 'phone_number', 'employment_status', 'credit_score']
    search_fields = ['user__username', 'id_number', 'phone_number']
    list_filter = ['employment_status']

@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = ['applicant', 'loan_type', 'amount', 'term_months', 'status', 'application_date']
    list_filter = ['status', 'loan_type', 'application_date']
    search_fields = ['applicant__username', 'purpose']
    readonly_fields = ['application_date', 'approved_date']

@admin.register(LoanDocument)
class LoanDocumentAdmin(admin.ModelAdmin):
    list_display = ['loan_application', 'document_type', 'verified', 'uploaded_at']
    list_filter = ['document_type', 'verified']
    search_fields = ['loan_application__applicant__username']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['user__username', 'title']
    readonly_fields = ['created_at']

@admin.register(LoanWithdrawal)
class LoanWithdrawalAdmin(admin.ModelAdmin):
    list_display = ['loan_application', 'mpesa_number', 'amount', 'status', 'withdrawal_date']
    list_filter = ['status', 'withdrawal_date']
    readonly_fields = ['withdrawal_date', 'processed_date']

@admin.register(LoanPayment)
class LoanPaymentAdmin(admin.ModelAdmin):
    list_display = ['loan_application', 'amount', 'due_date', 'status', 'payment_method', 'payment_date']
    list_filter = ['status', 'payment_method', 'due_date']
    search_fields = ['loan_application__applicant__username', 'transaction_id']
    readonly_fields = ['payment_date']