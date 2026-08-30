from django import forms


class CustomerUploadForm(forms.Form):
    file = forms.FileField(
        label='Upload Customer Data',
        help_text='Supported formats: CSV, Excel (.xlsx, .xls)',
        widget=forms.FileInput(attrs={
            'accept': '.csv,.xlsx,.xls',
            'class': 'form-control'
        })
    )


class UsedPointsUploadForm(forms.Form):
    file = forms.FileField(
        label='Upload Used Points Data',
        help_text='Supported formats: CSV, Excel (.xlsx, .xls)',
        widget=forms.FileInput(attrs={
            'accept': '.csv,.xlsx,.xls',
            'class': 'form-control'
        })
    )


class SalesUploadForm(forms.Form):
    file = forms.FileField(
        label='Upload Sales Data',
        help_text='Supported formats: CSV, Excel (.xlsx, .xls)',
        widget=forms.FileInput(attrs={
            'accept': '.csv,.xlsx,.xls',
            'class': 'form-control'
        })
    )


class SaleDetailUploadForm(forms.Form):
    file = forms.FileField(
        label='Upload Sale Detail Data',
        help_text='Supported formats: CSV, Excel (.xlsx, .xls)',
        widget=forms.FileInput(attrs={
            'accept': '.csv,.xlsx,.xls',
            'class': 'form-control'
        })
    )


class InventoryUploadForm(forms.Form):
    file = forms.FileField(
        label='Upload Inventory Data',
        help_text='Supported formats: CSV, Excel (.xlsx, .xls)',
        widget=forms.FileInput(attrs={
            'accept': '.csv,.xlsx,.xls',
            'class': 'form-control'
        })
    )


class MembershipBackfillForm(forms.Form):
    file = forms.FileField(
        label='Historical Customer Export',
        help_text='Same column format as the main customer import (VIP ID, PHONE NO., VIP GRADE, ...).',
        widget=forms.FileInput(attrs={
            'accept': '.csv,.xlsx,.xls',
            'class': 'form-control'
        })
    )
    snapshot_date = forms.DateField(
        label='Snapshot Date (historical, as-of date this file represents)',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    note = forms.CharField(
        label='Note',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Q1 2025 export'})
    )