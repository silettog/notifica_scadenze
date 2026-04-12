from datetime import datetime
from collections import defaultdict
from logger import logger
import config
import utils
import github_api as graphql

def notify_expiring_issues():
    excluded_statuses = [s.strip().lower() for s in getattr(config, 'excluded_statuses', "").split(",") if s.strip()]
    notifications_map = defaultdict(list)
    extra_emails = [e.strip() for e in getattr(config, 'mail_aggiuntive', '').split(',') if e.strip()]
    
    try:
        # IMPOSTIAMO open_only=False PER VEDERE TUTTE LE 13 ISSUE
        issues = graphql.get_project_issues(
            owner=config.repository_owner,
            owner_type=config.repository_owner_type,
            project_number=config.project_number,
            duedate_field_name=config.duedate_field_name,
            task_status_field_name=config.task_status_field_name,
            filters={'open_only': False} 
        )
    except Exception as e:
        logger.error(f"Errore: {e}")
        return

    logger.info(f"--- CENSIMENTO TOTALE: {len(issues)} ELEMENTI TROVATI ---")

    for idx, item in enumerate(issues, 1):
        issue_data = item.get('content', {})
        typename = issue_data.get('__typename', 'Unknown')
        num = issue_data.get('number', 'BOZZA')
        title = issue_data.get('title', 'Senza Titolo')
        state = issue_data.get('state', 'N/A')
        
        status_obj = item.get('statusValue')
        current_status = status_obj.get('name', 'N/A') if status_obj else 'N/A'
        
        date_field = item.get('fieldValueByName')
        date_val = date_field.get('date') if date_field else None

        # Questo log ci dirà la verità su ogni issue
        logger.info(f"{idx}) [{typename}] #{num} | Stato: {state} | Colonna: {current_status} | Data: {date_val}")

        # Se è una bozza (DraftIssue), non possiamo mandare il link corretto, quindi la saltiamo dopo il log
        if typename == 'DraftIssue':
            logger.warning(f"   >> Ignorata: #{num} è una BOZZA. Convertila in Issue su GitHub!")
            continue

        # Logica di filtraggio standard
        if current_status.lower() in excluded_statuses:
            continue
        if state != 'OPEN':
            logger.info(f"   >> Ignorata: È in stato {state}")
            continue
        if not date_val:
            continue

        # Calcolo date...
        duedate_obj = datetime.strptime(date_val, "%Y-%m-%d").date()
        days_diff = (duedate_obj - datetime.now().date()).days
        
        msg_type = None
        if 0 <= days_diff <= config.giorni_preavviso:
            msg_type = "IN SCADENZA"
        elif days_diff < 0:
            msg_type = "SCADUTA"

        if msg_type:
            issue_info = {
                'number': num, 'title': title, 'url': issue_data.get('url'),
                'duedate': duedate_obj, 'type': msg_type, 'delay': abs(days_diff)
            }
            recipients = set([a['email'] for a in issue_data.get('assignees', {}).get('nodes', []) if a.get('email')] + extra_emails)
            for email in recipients:
                notifications_map[email].append(issue_info)

    if notifications_map:
        send_aggregated_emails(notifications_map, "Riepilogo Scadenze")
    else:
        logger.info("Nessuna notifica da inviare.")

def send_aggregated_emails(notifications_map, subject_prefix):
    # (Stessa logica robusta discussa in precedenza)
    for email, items in notifications_map.items():
        subject = f"{subject_prefix} ({len(items)} attività)"
        html_rows = ""
        for i in items:
            color = "#D32F2F" if i['type'] == 'SCADUTA' else "#F57C00"
            html_rows += f"<tr><td style='padding:10px; border-bottom:1px solid #ddd;'><b style='color:{color}'>[{i['type']}]</b> #{i['number']} - {i['title']} ({i['duedate']})</td></tr>"
        
        full_html = f"<html><body><table style='width:100%; border-collapse:collapse;'>{html_rows}</table></body></html>"
        utils.send_email(config.smtp_from_email, [email], subject, full_html)
        logger.info(f"Email inviata a {email}")

def main():
    logger.info('--- Inizio Processo ---')
    notify_expiring_issues()
    logger.info('--- Fine Processo ---')

if __name__ == "__main__":
    main()
