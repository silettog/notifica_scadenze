from datetime import datetime
from collections import defaultdict
from logger import logger
import config
import utils
import github_api as graphql

def notify_expiring_issues():
    excluded_statuses = [s.strip().lower() for s in getattr(config, 'excluded_statuses', "").split(",") if s.strip()]
    notifications_map = defaultdict(list)
    full_project_list = []
    extra_emails = [e.strip() for e in getattr(config, 'mail_aggiuntive', '').split(',') if e.strip()]
    
    try:
        # Recuperiamo tutto (OPEN e CLOSED) per il censimento
        issues = graphql.get_project_issues(
            owner=config.repository_owner,
            owner_type=config.repository_owner_type,
            project_number=config.project_number,
            duedate_field_name=config.duedate_field_name,
            task_status_field_name=config.task_status_field_name,
            filters={'open_only': False}
        )
    except Exception as e:
        logger.error(f"Errore critico: {e}")
        return

    logger.info(f"--- ANALISI DI {len(issues)} ELEMENTI ---")

    for item in issues:
        issue_data = item.get('content', {})
        if not issue_data:
            continue
            
        typename = issue_data.get('__typename')
        if typename == 'DraftIssue':
            continue

        num = issue_data.get('number')
        title = issue_data.get('title')
        state = issue_data.get('state', 'UNKNOWN')
        url = issue_data.get('url', '')
        
        status_obj = item.get('statusValue')
        current_status = status_obj.get('name', 'N/A') if status_obj else 'N/A'
        
        date_field = item.get('fieldValueByName')
        date_val = date_field.get('date') if date_field else None

        # --- LOGICA ANOMALIA ---
        is_in_excluded = current_status.lower() in excluded_statuses
        anomaly_msg = ""
        if state == 'CLOSED' and not is_in_excluded:
            anomaly_msg = f"Incongruenza: Chiusa ma in colonna '{current_status}'"
        elif state == 'OPEN' and is_in_excluded:
            anomaly_msg = "Incongruenza: In colonna finale ma ancora Aperta"

        # Dati per report integrale
        full_project_list.append({
            'number': num,
            'title': title,
            'status': current_status,
            'state': state,
            'duedate': date_val or 'N.D.',
            'anomaly': anomaly_msg
        })

        # Logica scadenze (solo se OPEN)
        if state == 'OPEN' and not is_in_excluded and date_val:
            duedate_obj = datetime.strptime(date_val, "%Y-%m-%d").date()
            days_diff = (duedate_obj - datetime.now().date()).days
            
            msg_type = None
            if 0 <= days_diff <= config.giorni_preavviso:
                msg_type = "IN SCADENZA"
            elif days_diff < 0:
                msg_type = "SCADUTA"

            if msg_type:
                issue_info = {
                    'number': num, 'title': title, 'url': url,
                    'duedate': duedate_obj, 'type': msg_type, 
                    'delay': abs(days_diff), 'anomaly': anomaly_msg
                }
                assignees = issue_data.get('assignees', {}).get('nodes', [])
                emails = [a['email'] for a in assignees if a.get('email')]
                recipients = set(emails + extra_emails)
                for email in recipients:
                    notifications_map[email].append(issue_info)

    # Invio notifiche scadenze
    if notifications_map:
        send_aggregated_emails(notifications_map)
    
    # Invio report integrale a mail_aggiuntive
    if extra_emails and full_project_list:
        send_full_summary_email(extra_emails, full_project_list)

def send_full_summary_email(to_emails, issue_list):
    rows = ""
    for i in issue_list:
        bg = "background-color: #fff4f4;" if i['anomaly'] else ""
        rows += f"<tr style='{bg}'>"
        rows += f"<td style='border:1px solid #ddd; padding:5px;'>#{i['number']}</td>"
        rows += f"<td style='border:1px solid #ddd; padding:5px;'>{i['title']}</td>"
        rows += f"<td style='border:1px solid #ddd; padding:5px;'>{i['status']} ({i['state']})</td>"
        rows += f"<td style='border:1px solid #ddd; padding:5px;'>{i['duedate']}</td>"
        rows += f"<td style='border:1px solid #ddd; padding:5px; color:red;'>{i['anomaly']}</td>"
        rows += "</tr>"

    html = f"<html><body><h3>Report Integrale</h3><table style='width:100%; border-collapse:collapse;'>{rows}</table></body></html>"
    utils.send_email(config.smtp_from_email, to_emails, "Report Integrale Progetto", html)

def send_aggregated_emails(notifications_map):
    for email, items in notifications_map.items():
        rows = ""
        for i in items:
            color = "#D32F2F" if i['type'] == 'SCADUTA' else "#F57C00"
            rows += f"<tr><td style='border-bottom:1px solid #ddd; padding:10px;'>"
            rows += f"<b style='color:{color};'>[{i['type']}]</b> #{i['number']} - {i['title']}<br>"
            rows += f"Scadenza: {i['duedate']} <br><span style='color:red;'>{i['anomaly']}</span>"
            rows += f"</td><td style='text-align:right;'><a href='{i['url']}'>Apri</a></td></tr>"
        
        html = f"<html><body><table style='width:100%;'>{rows}</table></body></html>"
        utils.send_email(config.smtp_from_email, [email], "Notifica Scadenze", html)

def main():
    logger.info("--- Inizio Processo ---")
    notify_expiring_issues()
    logger.info("--- Fine Processo ---")

if __name__ == "__main__":
    main()
