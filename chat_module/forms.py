from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FileField, SelectMultipleField
from wtforms.validators import DataRequired, Length, Optional


class CreateGroupForm(FlaskForm):
    group_name = StringField("Group Name", validators=[DataRequired(), Length(max=100)])
    members = SelectMultipleField("Members", coerce=int, validators=[DataRequired()])


class ChatMessageForm(FlaskForm):
    content = TextAreaField("Message", validators=[DataRequired(), Length(max=5000)])
    attachment = FileField("Attachment", validators=[Optional()])

