from django import forms

from ops.models import ThresholdRule


class ThresholdRuleForm(forms.ModelForm):
    class Meta:
        model = ThresholdRule
        fields = ["warning_value", "critical_value", "unit_symbol", "is_active"]
        widgets = {
            "warning_value": forms.NumberInput(attrs={"step": "0.1"}),
            "critical_value": forms.NumberInput(attrs={"step": "0.1"}),
            "unit_symbol": forms.TextInput(),
        }
