from datetime import datetime
from collections import defaultdict
from logger import logger
import config
import utils
import github_api as graphql
import os
import json

# Caricamento Mapping Utenti
def load_user_map():
    path = os.path.join(os.path.dirname(__file__), 'users.json')
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    print("⚠️ File users.json non trovato. Le email verranno inviate solo ai destinatari fissi.")
    return {}


def notify_expiring_issues():
    excluded_statuses = [s.strip().lower() for s in getattr(config, 'excluded_statuses', "").split(",") if s.strip()]
    notifications_map = defaultdict(list)
    full_project_list = []
    extra_emails = [e.strip() for e in getattr(config, 'mail_aggiuntive', '').split(',') if e.strip()]
    USER_MAP = load_user_map()
    
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
            anomaly_msg = f"Incongruenza: Issue Chiusa ma in stato '{current_status}'"
        elif state == 'OPEN' and is_in_excluded:
            anomaly_msg = f"Incongruenza: In Status '{current_status}' ma Issue ancora Aperta"

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
                
                # --- MODIFICA QUI: Recupero email tramite mapping ---
                assignees = issue_data.get('assignees', {}).get('nodes', [])
                
                emails_da_mapping = []
                for a in assignees:
                    username = a.get('login')
                    # Cerca l'email nel dizionario caricato da users.json
                    email_trovata = USER_MAP.get(username)
                    if email_trovata:
                        emails_da_mapping.append(email_trovata)
                    else:
                        print(f"ℹ️ Nessun mapping trovato per l'utente: {username}")

                # Unisci le email ricavate dagli assignees con quelle fisse (extra_emails)
                recipients = set(emails_da_mapping + extra_emails)
                
                for email in recipients:
                    notifications_map[email].append(issue_info)

    # Invio notifiche scadenze
    if notifications_map:
        send_aggregated_emails(notifications_map)
    
    # Invio report integrale a mail_aggiuntive
    if extra_emails and full_project_list:
        send_full_summary_email(extra_emails, full_project_list)

def send_full_summary_email(to_emails, issue_list):
    """
    Invia il report integrale con righe azzurre per i task attivi.
    """
    excluded_statuses = [s.strip().lower() for s in getattr(config, 'excluded_statuses', "").split(",") if s.strip()]
    subject = f"📊 Report Integrale Progetto: {getattr(config, 'project_name', 'GitHub')}"
    
    header_html = """
        <thead>
            <tr style='background-color: #f2f2f2; text-align: left;'>
                <th style='border:1px solid #ddd; padding:10px;'>ID</th>
                <th style='border:1px solid #ddd; padding:10px;'>Titolo</th>
                <th style='border:1px solid #ddd; padding:10px;'>Colonna (Stato)</th>
                <th style='border:1px solid #ddd; padding:10px;'>Scadenza</th>
                <th style='border:1px solid #ddd; padding:10px;'>Anomalie/Note</th>
            </tr>
        </thead>
    """
    
    rows = ""
    for i in issue_list:
        # Determiniamo il colore della riga
        is_excluded = i['status'].lower() in excluded_statuses
        
        if i['anomaly']:
            bg_color = "#fff4f4"  # Rosso chiaro per anomalie
        elif not is_excluded:
            bg_color = "#e1f5fe"  # Azzurro per task attivi (non esclusi)
        else:
            bg_color = "#ffffff"  # Bianco per task conclusi (esclusi)

        rows += f"""
            <tr style='background-color: {bg_color};'>
                <td style='border:1px solid #ddd; padding:8px;'>#{i['number']}</td>
                <td style='border:1px solid #ddd; padding:8px;'>{i['title']}</td>
                <td style='border:1px solid #ddd; padding:8px;'>{i['status']} ({i['state']})</td>
                <td style='border:1px solid #ddd; padding:8px;'>{i['duedate']}</td>
                <td style='border:1px solid #ddd; padding:8px; color:red; font-weight:bold;'>{i['anomaly']}</td>
            </tr>
        """

    full_html = f"""
<html>
<body style='font-family: sans-serif; color: #333;'>
    <h3 style='color: #0366d6;'>📊 Riepilogo Stato Progetto</h3>
    <table style='width:100%; border-collapse:collapse; font-size:13px;'>
        {header_html}
        <tbody>
            {rows}
        </tbody>
    </table>
</body>
</html>
""".strip()

    if not config.dry_run:
        # Inviato solo come HTML
        utils.send_email(config.smtp_from_email, to_emails, subject, full_html)
        logger.info(f"Report integrale inviato a {to_emails}")

def send_aggregated_emails(notifications_map):
    """
    Invia le notifiche di scadenza (solo HTML).
    """
    for email, items in notifications_map.items():
        subject = f"Notifica Scadenze ({len(items)} attività)"
        html_rows = ""
        for i in items:
            color = "#D32F2F" if i['type'] == 'SCADUTA' else "#F57C00"
            anomaly_tag = f"<br><span style='color:red; font-size:11px;'>{i['anomaly']}</span>" if i['anomaly'] else ""
            
            html_rows += f"""
                <tr>
                    <td style='padding:10px; border-bottom:1px solid #ddd; background-color: #f9f9f9;'>
                        <b style='color:{color};'>[{i['type']}]</b> #{i['number']} - {i['title']}{anomaly_tag}<br>
                        <small>Data prevista: {i['duedate']}</small>
                    </td>
                    <td style='padding:10px; border-bottom:1px solid #ddd; text-align:right; background-color: #f9f9f9;'>
                        <a href='{i['url']}' style='background:#0366d6; color:white; padding:5px 10px; text-decoration:none; border-radius:3px;'>Apri</a>
                    </td>
                </tr>
            """

        full_html = f"<html><body><table style='width:100%; border-collapse:collapse;'>{html_rows}</table></body></html>"
        
        if not config.dry_run:
            utils.send_email(config.smtp_from_email, [email], subject, full_html)


def main():
    logger.info("--- Inizio Processo ---")
    notify_expiring_issues()
    logger.info("--- Fine Processo ---")

if __name__ == "__main__":
    main()
