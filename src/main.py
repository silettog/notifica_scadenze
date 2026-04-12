from datetime import datetime, timedelta
from logger import logger
import config
import utils
import graphql


def notify_expiring_issues():
    """
    Monitora le issue in scadenza o scadute e invia notifiche mirate.
    Ottimizzato per esecuzione settimanale (ogni venerdì).
    """
    # 1. PREPARAZIONE E RECUPERO DATI
    excluded_statuses = [s.strip().lower() for s in getattr(config, 'excluded_statuses', "done").split(",") if s]
    issues = []
    
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
        logger.error(f"Errore nel recupero delle issue: {e}")
        return

    if not issues:
        logger.info('Nessuna issue trovata.')
        return

    # 2. ELABORAZIONE ISSUE
    for item in issues:
        # Estrazione dati in base alla struttura (Enterprise vs Standard)
        if config.is_enterprise:
            projectItem = item
            issue_data = item['content']
        else:
            projectNodes = item.get('projectItems', {}).get('nodes', [])
            projectItem = next((entry for entry in projectNodes if entry['project']['number'] == config.project_number), None)
            issue_data = item

        if not projectItem:
            continue

        # --- FILTRO STATUS ---
        if 'statusValue' in projectItem and projectItem['statusValue']:
            current_status = projectItem['statusValue'].get('name', '').lower()
            if current_status in excluded_statuses:
                logger.debug(f"Salto issue #{issue_data['number']} (Stato: {current_status})")
                continue

        # --- CALCOLO DATE ---
        if not projectItem.get('fieldValueByName') or not projectItem['fieldValueByName'].get('date'):
            continue

        duedate_str = projectItem["fieldValueByName"]["date"]
        duedate_obj = datetime.strptime(duedate_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        
        days_diff = (duedate_obj - today).days # Positivo = futuro, Negativo = passato
        delay_days = abs(days_diff)

        # --- LOGICA DI NOTIFICA (OTTIMIZZATA PER IL VENERDÌ) ---
        msg_type = None
        label_ritardo = ""

        # Caso A: Scadenza imminente (nel futuro)
        if 0 <= days_diff <= config.giorni_preavviso:
            msg_type = "EXPIRING"
        
        # Caso B: Già scaduta (nel passato) - Gestione per intervalli
        elif days_diff < 0:
            if 1 <= delay_days < 7:
                msg_type = "OVERDUE"
                label_ritardo = "1-6 giorni"
            elif 7 <= delay_days < 15:
                msg_type = "OVERDUE"
                label_ritardo = "7-14 giorni"
            elif 15 <= delay_days < 30:
                msg_type = "OVERDUE"
                label_ritardo = "15-29 giorni"
            elif delay_days >= 30:
                msg_type = "OVERDUE"
                label_ritardo = "oltre 30 giorni"

        if not msg_type:
            continue

        # --- 3. COSTRUZIONE MESSAGGIO E INVIO ---
        assignees = issue_data.get('assignees', {}).get('nodes', [])
        
        if msg_type == "OVERDUE":
            subject = f"⚠️ SOLLECITO RITARDO: Issue #{issue_data['number']}"
            message = f'''
            <html>
                <body>
                    <h2 style="color: #D32F2F;">⚠️ Attività Scaduta</h2>
                    <p>L'attività <b>{issue_data['title']}</b> nel progetto <b>{getattr(config, 'project_name', 'Project')}</b> è scaduta il {duedate_obj}.</p>
                    <p>Attualmente risulta un ritardo di <b>{label_ritardo}</b>.</p>
                    <p>Si prega di completare il task o aggiornare la data di scadenza.</p>
                    <hr>
                    <p>Link alla issue: <a href="{issue_data['url']}">{issue_data['number']}</a></p>
                </body>
            </html>
            '''
            # Per il ritardo inviamo a tutti gli assegnatari
            to_emails = [a['email'] for a in assignees if a.get('email')]
        else:
            # Messaggio standard per scadenza imminente
            subject, message, to_emails = utils.prepare_expiring_issue_email_message(
                issue=issue_data, 
                assignees=assignees, 
                duedate=duedate_obj,
                project_name=getattr(config, 'project_name', 'Project')
            )

        # --- 4. INVIO EFFETTIVO ---
        if config.notification_type == 'email' and to_emails:
            if not config.dry_run:
                utils.send_email(
                    from_email=config.smtp_from_email,
                    to_email=to_emails,
                    subject=subject,
                    html_body=message
                )
                logger.info(f"Notifica {msg_type} inviata per #{issue_data['number']} a {to_emails}")
            else:
                logger.info(f"[DRY-RUN] Notifica {msg_type} pronta per #{issue_data['number']} ({label_ritardo if label_ritardo else 'in scadenza'})")


def notify_missing_duedate():
    issues = graphql.get_project_issues(
        owner=config.repository_owner,
        owner_type=config.repository_owner_type,
        project_number=config.project_number,
        duedate_field_name=config.duedate_field_name,
        task_status_field_name=config.task_status_field_name,
        filters={'empty_duedate': True, 'open_only': True}
    )

    # Check if there are issues available
    if not issues:
        logger.info('No issues has been found')
        return

    for projectItem in issues:
        # if projectItem['id'] != 'MDEzOlByb2plY3RWMkl0ZW0xMzMxOA==':
        #     continue
        issue = projectItem['content']

        # Get the list of assignees
        assignees = issue['assignees']['nodes']

        if config.notification_type == 'comment':
            # Prepare the notification content
            comment = utils.prepare_missing_duedate_comment(
                issue=issue,
                assignees=assignees
            )

            if not config.dry_run:
                # Add the comment to the issue
                graphql.add_issue_comment(issue['id'], comment)

            logger.info(f'Comment added to issue #{issue["number"]} ({issue["id"]})')
        elif config.notification_type == 'email':
            # Prepare the email content
            subject, message, to = utils.prepare_missing_duedate_email_message(
                issue=issue,
                assignees=assignees
            )

            if not config.dry_run:
                # Send the email
                utils.send_email(
                    from_email=config.smtp_from_email,
                    to_email=to,
                    subject=subject,
                    html_body=message
                )
            logger.info(f'Email sent to {to} for issue #{issue["number"]}')


def main():
    logger.info('Process started...')
    if config.dry_run:
        logger.info('DRY RUN MODE ON!')

    if config.notify_for == 'expiring_issues':
        notify_expiring_issues()
    elif config.notify_for == 'missing_duedate':
        notify_missing_duedate()
    else:
        raise Exception('Unsupported value for argument \'notify_for\'')


if __name__ == "__main__":
    main()
