from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, MultipleFileField, HiddenField, SelectField
from wtforms.validators import DataRequired, Optional, Length


class ComposeEmailForm(FlaskForm):
    recipient = StringField("To", validators=[DataRequired(), Length(max=255)])
    subject = StringField("Subject", validators=[DataRequired(), Length(max=255)])
    body = TextAreaField("Message", validators=[Optional()])
    label = StringField("Label", validators=[Optional(), Length(max=50)])
    draft_id = HiddenField("Draft ID")
    attachments = MultipleFileField("Attachments")

