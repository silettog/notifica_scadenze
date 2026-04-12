from datetime import datetime
from collections import defaultdict
from logger import logger
import config
import utils
import github_api as graphql

def notify_expiring_issues():
    """
    Versione con LOG POTENZIATI per capire perché la issue #48 sparisce.
    """
    excluded_statuses = [s.strip().lower() for s in getattr(config, 'excluded_statuses', "done").split(",") if s.strip()]
    notifications_map = defaultdict(list)
    extra_emails = [e.strip() for e in getattr(config, 'mail_aggiuntive', '').split(',') if e.strip()]
    
    logger.info(f"Filtri attivi: Status esclusi={excluded_statuses}, Giorni preavviso={config.giorni_preavviso}")

    try:
        if config.is_enterprise:
            issues = graphql.get_project_issues(
                owner=config.repository_owner,
                owner_type=config.repository_owner_type,
                project_number=config.project_number,
                duedate_field_name=config.duedate_field_name,
                task_status_field_name=config.task_status_field_name,
                filters={'open_only': True}
            )
        else:
            issues = graphql.get_repo_issues(
                owner=config.repository_owner,
                repository=config.repository_name,
                duedate_field_name=config.duedate_field_name,
                task_status_field_name=config.task_status_field_name
            )
    except Exception as e:
        logger.error(f"ERRORE CRITICO API: {e}")
        return

    if not issues:
        logger.warning(f"L'API non ha restituito nessuna issue per il progetto #{config.project_number}. Verifica che le issue siano effettivamente inserite nel progetto.")
        return

    logger.info(f"Trovate {len(issues)} issue totali nel progetto. Inizio analisi...")

    for item in issues:
        try:
            # Estrazione dati
            if config.is_enterprise:
                projectItem = item
                issue_data = item.get('content', {})
            else:
                projectNodes = item.get('projectItems', {}).get('nodes', [])
                projectItem = next((entry for entry in projectNodes if entry['project']['number'] == config.project_number), None)
                issue_data = item

            if not issue_data: continue
            
            num = issue_data.get('number')
            title = issue_data.get('title')

            # --- LOG DI DEBUG PER LA 42 ---
            is_target = (num == 42)
            if is_target:
                logger.info(f"--- ANALISI TARGET ISSUE #42 ---")

            # 1. Verifica Stato
            status_obj = projectItem.get('statusValue')
            current_status = status_obj.get('name', '').lower() if status_obj else 'n/a'
            
            if is_target: logger.info(f"Status: {current_status}")
            
            if current_status in excluded_statuses:
                if is_target: logger.warning("Esito: Saltata (Stato escluso)")
                continue

            # 2. Verifica Data (IL PUNTO CRITICO)
            date_field = projectItem.get('fieldValueByName')
            if is_target: logger.info(f"Dati campo data: {date_field}")

            if not date_field or not date_field.get('date'):
                if is_target: logger.error(f"Esito: Saltata (Campo '{config.duedate_field_name}' non trovato o vuoto)")
                continue

            duedate_str = date_field['date']
            duedate_obj = datetime.strptime(duedate_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            days_diff = (duedate_obj - today).days

            if is_target: logger.info(f"Data: {duedate_obj} (Diff: {days_diff} giorni)")

            # Logica scadenze
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
                if is_target: logger.info("Esito: Saltata (Non ancora in scadenza)")
                continue

            # 3. Raccolta Destinatari
            issue_info = {
                'number': num, 'title': title, 'url': issue_data.get('url'),
                'duedate': duedate_obj, 'type': msg_type, 'delay': label_ritardo
            }

            assignees = issue_data.get('assignees', {}).get('nodes', [])
            emails = [a['email'] for a in assignees if a.get('email')]
            recipients = set(emails + extra_emails)

            if is_target: logger.info(f"Esito: OK! Destinatari: {recipients}")

            for email in recipients:
                notifications_map[email].append(issue_info)

        except Exception as e:
            logger.error(f"Errore elaborazione issue {num}: {e}")

    # 2. INVIO
    if notifications_map:
        send_aggregated_emails(notifications_map, f"Riepilogo Scadenze {getattr(config, 'project_name', 'Progetto')}")
    else:
        logger.info("Nessuna notifica da inviare (notifications_map vuota).")


def notify_missing_duedate():
    # ... (stessa logica di notify_expiring_issues, mantenendo set(emails + extra_emails)) ...
    pass

def send_aggregated_emails(notifications_map, subject_prefix):
    """
    Invia le email aggregate con gestione rigorosa degli apici.
    """
    for email, items in notifications_map.items():
        # Calcoliamo il numero di item per l'oggetto
        num_items = len(items)
        subject = f"{subject_prefix} ({num_items} item)"
        
        html_rows = ""
        for i in items:
            # 1. Usiamo variabili d'appoggio per evitare logica complessa dentro la f-string
            msg_type = i['type']
            issue_num = i['number']
            issue_title = i['title']
            issue_url = i['url']
            issue_date = i['duedate']
            delay_label = i['delay']
            
            # 2. Scegliamo il colore in base al tipo
            color = "#D32F2F" if msg_type in ["SCADUTA", "DATA MANCANTE"] else "#F57C00"
            
            # 3. Prepariamo la label del ritardo (se esiste)
            delay_html = f"<b>{delay_label}</b>" if delay_label else ""
            
            # Costruzione della riga: Usiamo tripli doppi apici fuori e apici SINGOLI dentro
            html_rows += f"""
                <tr>
                    <td style='padding: 10px; border-bottom: 1px solid #ddd;'>
                        <b style='color: {color};'>[{msg_type}]</b> #{issue_num} - {issue_title}<br>
                        <small>Scadenza: {issue_date} {delay_html}</small>
                    </td>
                    <td style='padding: 10px; border-bottom: 1px solid #ddd; text-align: right;'>
                        <a href='{issue_url}' style='background-color: #0366d6; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; font-size: 12px;'>Apri</a>
                    </td>
                </tr>
            """

        # Template finale: Anche qui, tripli doppi apici e strip() per evitare spazi bianchi iniziali
        project_name = getattr(config, 'project_name', 'Project')
        full_html = f"""
<html>
<body style='font-family: sans-serif; color: #333;'>
    <h2 style='border-bottom: 2px solid #eee; padding-bottom: 10px;'>Riepilogo Attività GitHub</h2>
    <p>Ciao, le seguenti attività nel progetto <b>{project_name}</b> richiedono attenzione:</p>
    <table style='width: 100%; border-collapse: collapse;'>
        {html_rows}
    </table>
    <p style='margin-top: 25px; font-size: 12px; color: #888;'>
        Notifica automatica - Non rispondere a questa email.
    </p>
</body>
</html>
""".strip()

        if not config.dry_run:
            utils.send_email(
                from_email=config.smtp_from_email,
                to_email=[email],
                subject=subject,
                html_body=full_html
            )
            logger.info(f"Email inviata con successo a {email}")
        else:
            logger.info(f"[DRY-RUN] Email pronta per {email} con {num_items} issue")

def main():
    logger.info('--- Inizio Processo Notifiche ---')
    if config.notify_for == 'expiring_issues':
        notify_expiring_issues()
    elif config.notify_for == 'missing_duedate':
        notify_missing_duedate()
    logger.info('--- Fine Processo ---')

if __name__ == "__main__":
    main()
