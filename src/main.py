from datetime import datetime
from collections import defaultdict
from logger import logger
import config
import utils
import github_api as graphql

def notify_expiring_issues():
    excluded_statuses = [s.strip().lower() for s in getattr(config, 'excluded_statuses', "done").split(",") if s.strip()]
    notifications_map = defaultdict(list)
    extra_emails = [e.strip() for e in getattr(config, 'mail_aggiuntive', '').split(',') if e.strip()]
    
    logger.info(f"Parametri: Preavviso={config.giorni_preavviso}gg, ExtraMail={extra_emails}")

    try:
        issues = graphql.get_project_issues(
            owner=config.repository_owner,
            owner_type=config.repository_owner_type,
            project_number=config.project_number,
            duedate_field_name=config.duedate_field_name,
            task_status_field_name=config.task_status_field_name,
            filters={'open_only': True}
        )
    except Exception as e:
        logger.error(f"Errore API: {e}")
        return

    if not issues:
        logger.warning("Nessuna issue restituita dall'API.")
        return

    logger.info(f"--- INIZIO ANALISI DI {len(issues)} ISSUE ---")

    for idx, item in enumerate(issues, 1):
        try:
            issue_data = item.get('content', {})
            num = issue_data.get('number', 'N/A')
            title = issue_data.get('title', 'Senza Titolo')
            
            # --- LOG SEMPRE ATTIVO PER OGNI ISSUE ---
            status_obj = item.get('statusValue')
            current_status = status_obj.get('name', 'N/A') if status_obj else 'N/A'
            
            date_field = item.get('fieldValueByName')
            date_val = date_field.get('date') if date_field else 'NON TROVATA'

            logger.info(f"Issue {idx}) #{num} | Stato: {current_status} | Data: {date_val}")

            # FILTRO 1: Stato
            if current_status.lower() in excluded_statuses:
                logger.info(f"   >> Saltata: Stato '{current_status}' escluso.")
                continue

            # FILTRO 2: Data mancante
            if date_val == 'NON TROVATA' or not date_val:
                logger.info(f"   >> Saltata: Data di scadenza non impostata.")
                continue

            # CALCOLO SCADENZA
            duedate_obj = datetime.strptime(date_val, "%Y-%m-%d").date()
            days_diff = (duedate_obj - datetime.now().date()).days
            
            msg_type = None
            label_ritardo = ""
            if 0 <= days_diff <= config.giorni_preavviso:
                msg_type = "IN SCADENZA"
            elif days_diff < 0:
                msg_type = "SCADUTA"
                delay = abs(days_diff)
                if delay < 7: label_ritardo = "1-6 giorni"
                elif delay < 15: label_ritardo = "7-14 giorni"
                elif delay < 30: label_ritardo = "15-29 giorni"
                else: label_ritardo = "oltre 30 giorni"

            if not msg_type:
                logger.info(f"   >> Saltata: Scade tra {days_diff} giorni (fuori intervallo).")
                continue

            # SE ARRIVA QUI, LA NOTIFICA È VALIDA
            issue_info = {
                'number': num, 'title': title, 'url': issue_data.get('url'),
                'duedate': duedate_obj, 'type': msg_type, 'delay': label_ritardo
            }

            assignees = issue_data.get('assignees', {}).get('nodes', [])
            emails = [a['email'] for a in assignees if a.get('email')]
            recipients = set(emails + extra_emails)

            logger.info(f"   >> OK! Notifica pronta per: {recipients}")

            for email in recipients:
                notifications_map[email].append(issue_info)

        except Exception as e:
            logger.error(f"Errore su issue {idx}: {e}")

    # INVIO AGGREGATO
    if notifications_map:
        send_aggregated_emails(notifications_map, "Riepilogo Scadenze")
    else:
        logger.info("--- FINE: Nessuna notifica generata ---")

def send_aggregated_emails(notifications_map, subject_prefix):
    # (Usa la versione corretta con gli apici dell'ultimo messaggio)
    for email, items in notifications_map.items():
        subject = f"{subject_prefix} ({len(items)} item)"
        html_rows = ""
        for i in items:
            color = "#D32F2F" if i['type'] == 'SCADUTA' else "#F57C00"
            html_rows += f"<tr><td><b style='color:{color}'>[{i['type']}]</b> #{i['number']} - {i['title']} ({i['duedate']})</td></tr>"
        
        full_html = f"<html><body><table>{html_rows}</table></body></html>"
        
        if not config.dry_run:
            utils.send_email(config.smtp_from_email, [email], subject, full_html)
            logger.info(f"Email inviata a {email}")
        else:
            logger.info(f"DRY-RUN: Email per {email} pronta.")

def main():
    logger.info('--- Inizio Processo ---')
    notify_expiring_issues()
    logger.info('--- Fine Processo ---')

if __name__ == "__main__":
    main()
