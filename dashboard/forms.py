from django import forms
from .models import LoanApplication, BorrowerProfile, LoanDocument, LoanType, LoanWithdrawal, LoanPayment
from django.contrib.auth.models import User
import os  # Add this import

class BorrowerProfileForm(forms.ModelForm):
    class Meta:
        model = BorrowerProfile
        fields = [
            'id_number', 
            'phone_number', 
            'date_of_birth', 
            'profile_picture',  # Add this field
            'employment_status', 
            'monthly_income', 
            'employer_name'
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'monthly_income': forms.NumberInput(attrs={'min': '0', 'step': '100'}),
            'profile_picture': forms.FileInput(attrs={
                'accept': '.jpg,.jpeg,.png,.gif',
                'class': 'form-control'
            })
        }
    
    def clean_profile_picture(self):
        profile_picture = self.cleaned_data.get('profile_picture')
        if profile_picture:
            # Check file size (2MB limit)
            if profile_picture.size > 2 * 1024 * 1024:
                raise forms.ValidationError('Profile picture size must be less than 2MB.')
            
            # Check file extension
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif']
            ext = os.path.splitext(profile_picture.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError('Unsupported file format. Please upload JPG, JPEG, PNG, or GIF files.')
        
        return profile_picture
    
class LoanApplicationForm(forms.ModelForm):
    class Meta:
        model = LoanApplication
        fields = ['loan_type', 'amount', 'term_months', 'purpose']
        widgets = {
            'amount': forms.NumberInput(attrs={'min': '1000', 'step': '100'}),
            'term_months': forms.NumberInput(attrs={'min': '1', 'max': '360'}),
            'purpose': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active loan types
        self.fields['loan_type'].queryset = LoanType.objects.filter(is_active=True)

class LoanDocumentForm(forms.ModelForm):
    class Meta:
        model = LoanDocument
        fields = ['document_type', 'document_file']
        widgets = {
            'document_file': forms.FileInput(attrs={
                'accept': '.jpg,.jpeg,.png,.pdf',
                'class': 'form-control'
            })
        }
    
    def clean_document_file(self):
        document_file = self.cleaned_data.get('document_file')
        if document_file:
            # Check file size (5MB limit)
            if document_file.size > 5 * 1024 * 1024:
                raise forms.ValidationError('File size must be less than 5MB.')
            
            # Check file extension
            valid_extensions = ['.jpg', '.jpeg', '.png', '.pdf']
            ext = os.path.splitext(document_file.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError('Unsupported file format. Please upload JPG, JPEG, PNG, or PDF files.')
        
        return document_file

class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

class LoanWithdrawalForm(forms.ModelForm):
    mpesa_number = forms.CharField(
        max_length=15,
        widget=forms.TextInput(attrs={
            'placeholder': '2547XXXXXXXX',
            'pattern': '2547\\d{8}',
            'title': 'Enter M-Pesa number in format 2547XXXXXXXX',
            'class': 'form-control'
        })
    )
    
    class Meta:
        model = LoanWithdrawal
        fields = ['mpesa_number']
    
    def clean_mpesa_number(self):
        mpesa_number = self.cleaned_data['mpesa_number']
        if not mpesa_number.startswith('2547') or len(mpesa_number) != 12:
            raise forms.ValidationError('Please enter a valid M-Pesa number starting with 2547 followed by 8 digits (e.g., 254712345678)')
        return mpesa_number

class LoanPaymentForm(forms.ModelForm):
    mpesa_number = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': '2547XXXXXXXX',
            'pattern': '2547\\d{8}',
            'title': 'Enter M-Pesa number in format 2547XXXXXXXX',
            'class': 'form-control'
        })
    )
    
    class Meta:
        model = LoanPayment
        fields = ['payment_method', 'mpesa_number', 'amount']
        widgets = {
            'amount': forms.NumberInput(attrs={'min': '100', 'step': '100', 'class': 'form-control'}),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.loan_application = kwargs.pop('loan_application', None)
        super().__init__(*args, **kwargs)
        
        if self.loan_application:
            # Set default amount to next due payment
            next_payment = self.loan_application.payments.filter(
                status__in=['pending', 'overdue']
            ).order_by('due_date').first()
            if next_payment:
                self.fields['amount'].initial = next_payment.amount
            else:
                # If no pending payments, set to minimum
                self.fields['amount'].initial = 100
    
    def clean_mpesa_number(self):
        payment_method = self.cleaned_data.get('payment_method')
        mpesa_number = self.cleaned_data.get('mpesa_number')
        
        if payment_method == 'mpesa' and not mpesa_number:
            raise forms.ValidationError('M-Pesa number is required for M-Pesa payments')
        
        if mpesa_number and (not mpesa_number.startswith('2547') or len(mpesa_number) != 12):
            raise forms.ValidationError('Please enter a valid M-Pesa number starting with 2547 followed by 8 digits (e.g., 254712345678)')
        
        return mpesa_number
    
    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount is None:
            raise forms.ValidationError('Amount is required')
            
        if amount < 100:
            raise forms.ValidationError('Minimum payment amount is KSh 100')
        
        if self.loan_application:
            remaining_balance = self.loan_application.remaining_balance
            if float(amount) > remaining_balance:
                raise forms.ValidationError(f'Payment amount cannot exceed remaining balance of KSh {remaining_balance:.2f}')
        
        return amount