from django import forms
from django.core.exceptions import ValidationError

from ops.models import ThresholdRule


class ThresholdRuleForm(forms.ModelForm):
    DESCENDING_RULE_TYPES = {
        ThresholdRule.RuleType.TANK_LOW,
    }

    class Meta:
        model = ThresholdRule
        fields = ["warning_value", "critical_value", "unit_symbol", "is_active"]
        widgets = {
            "warning_value": forms.NumberInput(attrs={"step": "0.1"}),
            "critical_value": forms.NumberInput(attrs={"step": "0.1"}),
            "unit_symbol": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        unit_field = self.fields.get("unit_symbol")
        if unit_field is not None:
            unit_field.disabled = True
            unit_field.required = False
            unit_field.widget.attrs.update({"readonly": True, "tabindex": -1})

    def clean(self):
        cleaned_data = super().clean()
        warning_value = cleaned_data.get("warning_value")
        critical_value = cleaned_data.get("critical_value")

        if warning_value is None or critical_value is None:
            return cleaned_data

        descending_rule = self.instance and self.instance.rule_type in self.DESCENDING_RULE_TYPES
        if descending_rule:
            if warning_value <= critical_value:
                error_message = "Warning threshold must be higher than critical for low-level alerts."
                self.add_error("warning_value", error_message)
                self.add_error("critical_value", error_message)
        elif warning_value >= critical_value:
            error_message = "Warning threshold must be lower than critical threshold."
            self.add_error("warning_value", error_message)
            self.add_error("critical_value", error_message)

        return cleaned_data
