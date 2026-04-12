from datetime import datetime
from collections import defaultdict
from logger import logger
import config
import utils
import github_api as graphql

def notify_expiring_issues():
    """
    Monitora le issue in scadenza o scadute e invia notifiche aggregate per utente.
    Ottimizzato per esecuzione periodica.
    """
    excluded_statuses = [s.strip().lower() for s in getattr(config, 'excluded_statuses', "done").split(",") if s.strip()]
    notifications_map = defaultdict(list)
    
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
        logger.error(f"Errore critico nel recupero delle issue (expiring): {e}")
        return

    if not issues:
        logger.info('Nessuna issue in scadenza trovata.')
        return

    # 1. ELABORAZIONE E RAGGRUPPAMENTO
    for item in issues:
        try:
            if config.is_enterprise:
                projectItem = item
                issue_data = item['content']
            else:
                projectNodes = item.get('projectItems', {}).get('nodes', [])
                projectItem = next((entry for entry in projectNodes if entry['project']['number'] == config.project_number), None)
                issue_data = item

            if not projectItem or not issue_data:
                continue

            # Filtro Status
            if 'statusValue' in projectItem and projectItem['statusValue']:
                current_status = projectItem['statusValue'].get('name', '').lower()
                if current_status in excluded_statuses:
                    continue

            # Calcolo Date
            if not projectItem.get('fieldValueByName') or not projectItem['fieldValueByName'].get('date'):
                continue

            duedate_str = projectItem["fieldValueByName"]["date"]
            duedate_obj = datetime.strptime(duedate_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            days_diff = (duedate_obj - today).days
            delay_days = abs(days_diff)

            msg_type = None
            label_ritardo = ""

            if 0 <= days_diff <= config.giorni_preavviso:
                msg_type = "IN SCADENZA"
            elif days_diff < 0:
                msg_type = "SCADUTA"
                if delay_days < 7: label_ritardo = "1-6 giorni"
                elif delay_days < 15: label_ritardo = "7-14 giorni"
                elif delay_days < 30: label_ritardo = "15-29 giorni"
                else: label_ritardo = "oltre 30 giorni"

            if not msg_type:
                continue

            assignees = issue_data.get('assignees', {}).get('nodes', [])
            to_emails = [a['email'] for a in assignees if a.get('email')]

            if not to_emails:
                logger.warning(f"Issue #{issue_data['number']} non ha email pubbliche. Salto.")
                continue

            for email in to_emails:
                notifications_map[email].append({
                    'number': issue_data['number'],
                    'title': issue_data['title'],
                    'url': issue_data['url'],
                    'duedate': duedate_obj,
                    'type': msg_type,
                    'delay': label_ritardo
                })
        except Exception as e:
            logger.error(f"Errore elaborazione issue {item.get('number', 'unknown')}: {e}")

    # 2. INVIO AGGREGATO
    send_aggregated_emails(notifications_map, "Riepilogo Scadenze GitHub")


def notify_missing_duedate():
    """
    Monitora le issue senza data di scadenza e invia notifiche.
    """
    notifications_map = defaultdict(list)
    
    try:
        issues = graphql.get_project_issues(
            owner=config.repository_owner,
            owner_type=config.repository_owner_type,
            project_number=config.project_number,
            duedate_field_name=config.duedate_field_name,
            task_status_field_name=config.task_status_field_name,
            filters={'empty_duedate': True, 'open_only': True}
        )
    except Exception as e:
        logger.error(f"Errore critico nel recupero delle issue (missing duedate): {e}")
        return

    if not issues:
        logger.info('Nessuna issue senza data trovata.')
        return

    for projectItem in issues:
        try:
            issue = projectItem['content']
            assignees = issue.get('assignees', {}).get('nodes', [])
            to_emails = [a['email'] for a in assignees if a.get('email')]

            if not to_emails:
                continue

            for email in to_emails:
                notifications_map[email].append({
                    'number': issue['number'],
                    'title': issue['title'],
                    'url': issue['url'],
                    'type': "DATA MANCANTE",
                    'duedate': "N.D.",
                    'delay': ""
                })
        except Exception as e:
            logger.error(f"Errore issue senza data #{projectItem.get('number')}: {e}")

    send_aggregated_emails(notifications_map, "⚠️ Azione richiesta: Date di scadenza mancanti")


def send_aggregated_emails(notifications_map, subject_prefix):
    """
    Funzione helper per inviare le email raggruppate.
    """
    for email, items in notifications_map.items():
        subject = f"{subject_prefix} ({len(items)} item)"
        
        html_rows = ""
        for i in items:
            color = "#D32F2F" if i['type'] in ["SCADUTA", "DATA MANCANTE"] else "#F57C00"
            delay_info = f"<b>{i['delay']}</b>" if i['delay'] else ""
            html_rows += f"""
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #ddd;">
                        <b style="color: {color};">[{i['type']}]</b> #{i['number']} - {i['title']}<br>
                        <small>Scadenza: {i['duedate']} {delay_info}</small>
                    </td>
                    <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: right;">
                        <a href="{i['url']}" style="background-color: #0366d6; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; font-size: 12px;">Apri</a>
                    </td>
                </tr>
            """

        full_html = f"""
        <html>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;">
                <h2 style="color: #333;">Riepilogo Attività GitHub</h2>
                <p>Ciao, le seguenti attività nel progetto <b>{getattr(config, 'project_name', 'Project')}</b> richiedono la tua attenzione:</p>
                <table style="width: 100%; border-collapse: collapse;">
                    {html_rows}
                </table>
                <p style="margin-top: 25px; font-size: 12px; color: #888;">
                    Questa è una notifica automatica inviata dal sistema di monitoraggio scadenze.
                </p>
            </body>
        </html>
        """

        if not config.dry_run:
            utils.send_email(
                from_email=config.smtp_from_email,
                to_email=[email],
                subject=subject,
                html_body=full_html
            )
            logger.info(f"Email inviata a {email} ({len(items)} issue)")
        else:
            logger.info(f"[DRY-RUN] Email per {email} ({len(items)} issue): {subject}")


def main():
    logger.info('--- Inizio Processo Notifiche ---')
    if config.dry_run:
        logger.info('MODALITÀ DRY-RUN ATTIVA: Nessuna email verrà inviata realmente.')

    try:
        if config.notify_for == 'expiring_issues':
            notify_expiring_issues()
        elif config.notify_for == 'missing_duedate':
            notify_missing_duedate()
        else:
            logger.error(f"Valore non supportato per notify_for: {config.notify_for}")
    except Exception as e:
        logger.error(f"Errore fatale durante l'esecuzione: {e}")
    
    logger.info('--- Fine Processo ---')


if __name__ == "__main__":
    main()
