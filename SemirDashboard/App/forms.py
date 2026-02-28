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