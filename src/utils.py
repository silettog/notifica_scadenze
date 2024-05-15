import smtplib
import html2text
import config
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logger import logger


def prepare_missing_duedate_comment(issue: dict, assignees: dict):
    """
    Prepare the comment from the given arguments and return it
    """
    comment = ''
    if assignees:
        for assignee in assignees:
            comment += f'@{assignee["login"]} '
    else:
        logger.info(f'No assignees found for issue #{issue["number"]}')

    comment += f'Kindly set the `Due Date` for this issue.'
    logger.info(f'Issue {issue["title"]} | {comment}')
    logger.info(f'***Esco da utils.prepare_missing_duedate_comment ***')
    return comment


def prepare_expiring_issue_comment(issue: dict, assignees: dict, duedate):
    """
    Prepare the comment from the given arguments and return it
    """
    comment = ''
    if assignees:
        for assignee in assignees:
            comment += f'@{assignee["login"]} '
    else:
        logger.info(f'No assignees found for issue #{issue["number"]}')

    comment += f'Questa issue deve essere consegnata entro il: {duedate.strftime("%b %d, %Y")}'
    logger.info(f'***Esco da utils.prepare_expiring_issue_comment *** Issue {issue["title"]} | {comment}')
    return comment


def prepare_missing_duedate_email_message(issue, assignees):
    """
    Prepare the email message, subject and mail_to addresses
    """
    subject = f'Re: [{config.repository}] {issue["title"]} (#{issue["number"]})'
    _assignees = ''
    mail_to = []
    if assignees:
        for assignee in assignees:
            _assignees += f'@{assignee["name"]} '
            mail_to.append(assignee['email'])
        #####################################   MESSAGGIO   ######################### 
        message = f'Assignees: {_assignees}' \
          f'<br>La issue \"{issue["title"]}\" non ha una scadenza'\
          f'<br> Per favore setta una scadenza (\"due date\") per questa issue sul progetto.' \
          f'<br><br>{issue["url"]}'\
          f'<br><br>{issue["body"]}'

    else:
        logger.info(f'No assignees found for issue #{issue["number"]}')
        #####################################   MESSAGGIO   ######################### 
        message = f'La issue \"{issue["title"]}\" non ha un responsabile' \
              f'<br>Per favore setta un responsabile (\"assignee\").' \
              f'<br><br>{issue["url"]}'
    logger.info(f'***esco da utils.prepare_missing_duedate_email_message*** {subject} * {message} * {mail_to}')
    return [subject, message, mail_to]


def prepare_expiring_issue_email_message(issue, assignees, duedate):
    """
    Prepare the email message, subject and mail_to addresses
    """
    subject = f'Re: [{config.repository}] {issue["title"]} (#{issue["number"]})'
    _assignees = ''
    mail_to = []
    if assignees:
        for assignee in assignees:
            _assignees += f'@{assignee["name"]} '
            mail_to.append(assignee['email'])
        logger.info(f'MAIL A: {mail_to}')
    else:
        logger.info(f'No assignees found for issue #{issue["number"]}')
    #####################################   MESSAGGIO   #########################  
    message = f'Assignees: {_assignees}' \
              f'<br>La issue \"{issue["title"]}\" deve essere consegnata entro il: {duedate.strftime("%b %d, %Y")}' \
              f'<br><br>{issue["url"]}'

    logger.info(f'***esco da utils.prepare_expiring_issue_email_message*** {subject} * {message} * {mail_to}')
    return [subject, message, mail_to]


def send_email(from_email: str, to_email: list, subject: str, html_body: str):
    smtp_server = smtplib.SMTP(config.smtp_server, config.smtp_port)
    smtp_server.starttls()
    smtp_server.login(config.smtp_username, config.smtp_password)

    # Create the plain text version of the email
    text_body = html2text.html2text(html_body)

    to_email.append(config.mail_aggiuntive)

    logger.info(f'MESSAGE-TO:  {to_email}')
    logger.info(f'MAIL AGGIUNTIVE:  {config.mail_aggiuntive}')

    #####################################   MESSAGGIO   ######################### 
    message = MIMEMultipart()
    message['From'] = from_email
    message['To'] = ", ".join(to_email)
    message['Subject'] = subject

    # Attach the plain text version
    # message.attach(MIMEText(text_body, 'plain'))

    # Attach the HTML version
    message.attach(MIMEText(html_body, 'html'))

    # Send the email
    text = message.as_string()
    smtp_server.sendmail(from_email, to_email, text)

    smtp_server.quit()
