import smtplib
import html2text
import config
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logger import logger

def clean_recipients(assignee_list, additional_mails_str):
    ###    Filtra e pulisce la lista dei destinatari rimuovendo duplicati e valori non validi.    ###
    final_emails = set()

    # 1. Estrazione email dagli assegnatari (se presenti)
    if assignee_list:
        for email in assignee_list:
            if email and isinstance(email, str) and "@" in email:
                final_emails.add(email.strip().lower())

    # 2. Gestione stringa mail aggiuntive (es. "mail1@test.it, mail2@test.it")
    if additional_mails_str:
        parts = additional_mails_str.split(',')
        for p in parts:
            clean_p = p.strip().lower()
            if "@" in clean_p:
                final_emails.add(clean_p)

    return list(final_emails)

def prepare_missing_duedate_comment(issue: dict, assignees: list):
    ###    Prepare the comment from the given arguments and return it    ###
    comment = ''
    if assignees:
        for assignee in assignees:
            # Protezione: verifica che l'oggetto assignee abbia la chiave 'login'
            login = assignee.get('login', 'unknown')
            comment += f'@{login} '
            #comment += f'@{assignee["login"]} '
    else:
        logger.info(f'No assignees found for issue #{issue["number"]}')

    comment += f'Kindly set the `Due Date` for this issue.'
    logger.info(f'Issue {issue["title"]} | {comment}')
    logger.info(f'***Esco da utils.prepare_missing_duedate_comment ***')
    return comment


def prepare_expiring_issue_comment(issue: dict, assignees: dict, duedate):
    ###    Prepare the comment from the given arguments and return it    ###
    comment = ''
    if assignees:
        for assignee in assignees:
            login = assignee.get('login', 'unknown')
            comment += f'@{login} '
            # comment += f'@{assignee["login"]} '
    else:
        logger.info(f'No assignees found for issue #{issue["number"]}')
    
    # Formattazione data italiana: GG/MM/AAAA
    date_str = duedate.strftime("%d/%m/%Y") if duedate else "N/A"
    comment += f'Questa issue deve essere consegnata entro il: {date_str}'
    #comment += f'Questa issue deve essere consegnata entro il: {duedate.strftime("%d/%m/%Y")}'
    logger.info(f'***Esco da utils.prepare_expiring_issue_comment *** Issue {issue["title"]} | {comment}')
    return comment


def prepare_missing_duedate_email_message(issue, assignees):
    ###    Prepara oggetto e corpo email per issue senza data    ###
    subject = f'Re: [{config.repository}] {issue["title"]} (#{issue.get("number")})'
    _assignees = ''
    mail_to = []
    _assignees_names = []
    
    if assignees:
        for assignee in assignees:
            _assignees_names.append(f"@{assignee.get('name', 'User')}")
            if assignee.get('email'):
                mail_to.append(assignee['email'])
        assignees_str = ", ".join(_assignees_names)

        #######   MESSAGGIO   #######
        message = (f'Assignees: {assignees_str}<br>'
                   f'La issue "{issue.get("title")}" non ha una scadenza prevista.<br>'
                   f'Per favore, imposta una "data consegna prevista" sul progetto.<br><br>'
                   f'<a href="{issue.get("url")}">Visualizza Issue su GitHub</a>')
       
    else:
        logger.info(f'No assignees found for issue #{issue["number"]}')
        #######   MESSAGGIO   ####### 
        message = (f'La issue "{issue.get("title")}" non ha un responsabile assegnato.<br>'
                   f'Per favore, assegna un responsabile ("assignee").<br><br>'
                   f'<a href="{issue.get("url")}">Visualizza Issue su GitHub</a>')
        
    logger.info(f'***esco da utils.prepare_missing_duedate_email_message*** {subject} * {message} * {mail_to}')
    return [subject, message, mail_to]


def prepare_expiring_issue_email_message(issue, assignees, duedate):
    ###    Prepara oggetto e corpo email per issue in scadenza.    ###
    subject = f'Re: [{config.repository}] {issue.get("title")} (#{issue.get("number")})'
    mail_to = []
    _assignees_names = []

    if assignees:
        for assignee in assignees:
            _assignees_names.append(f"@{assignee.get('name', 'User')}")
            if assignee.get('email'):
                mail_to.append(assignee['email'])
        logger.info(f'MAIL A: {mail_to}')
    else:
        logger.info(f'No assignees found for issue #{issue["number"]}')
        
    date_str = duedate.strftime("%d/%m/%Y") if duedate else "N/A"
    assignees_str = ", ".join(_assignees_names) if _assignees_names else "Nessuno"
    
    message = (f'Assignees: {assignees_str}<br>'
               f'La issue "{issue.get("title")}" deve essere consegnata entro il: <b>{date_str}</b><br><br>'
               f'Link: <a href="{issue.get("url")}">{issue.get("url")}</a>')
    logger.info(f'***esco da utils.prepare_expiring_issue_email_message*** {subject} * {message} * {mail_to}')
    return [subject, message, mail_to]



def send_email(from_email: str, to_email: list, subject: str, html_body: str):
    ### Invia l'email utilizzando i parametri in config.py con gestione errori.     ###
    
    # 1. Pulizia e unione destinatari
    destinatari = clean_recipients(to_email, config.mail_aggiuntive)
    
    if not destinatari:
        logger.warning(f"Salto invio: nessun destinatario valido per '{subject}'")
        return

    try:
        # 2. Connessione al server
        server = smtplib.SMTP(config.smtp_server, config.smtp_port)
        server.set_debuglevel(0) # Imposta a 1 per vedere i log dettagliati SMTP
        server.starttls()
        server.login(config.smtp_username, config.smtp_password)

        # 3. Costruzione del messaggio
        message = MIMEMultipart()
        message['From'] = from_email
        message['To'] = ", ".join(destinatari)
        message['Subject'] = subject
        
        # Versione solo testo (opzionale, utile per filtri antispam)
        text_body = html2text.html2text(html_body)
        message.attach(MIMEText(text_body, 'plain'))
        message.attach(MIMEText(html_body, 'html'))

        # 4. Invio
        server.sendmail(from_email, destinatari, message.as_string())
        server.quit()
        logger.info(f"Email inviata correttamente a: {len(destinatari)} destinatari.")

    except smtplib.SMTPAuthenticationError:
        logger.error("Errore Autenticazione SMTP: controlla username e password (o policy CSI).")
    except Exception as e:
        logger.error(f"Errore durante l'invio email: {e}")


