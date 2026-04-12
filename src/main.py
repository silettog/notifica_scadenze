from datetime import datetime, timedelta
from logger import logger
import config
import utils
import graphql

'''
def notify_expiring_issues():
    """
    # 1. Carica la lista degli status da escludere dal config (es: stringa separata da virgole)
    excluded_statuses = [s.strip().lower() for s in getattr(config, 'excluded_statuses', "").split(",") if s]

    if config.is_enterprise:
        issues = graphql.get_project_issues(
            owner=config.repository_owner,
            owner_type=config.repository_owner_type,
            project_number=config.project_number,
            duedate_field_name=config.duedate_field_name,
            # Passiamo anche il nome del campo status alla query GraphQL
            task_status_field_name=config.task_status_field_name, 
            filters={'open_only': True}
        )
    else:
        # ... (logica repo issues)
        pass
    """
    # 1. Inizializza SEMPRE la variabile all'inizio
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
            # FIX: Aggiunta la virgola mancante tra duedate_field_name e task_status_field_name
            issues = graphql.get_repo_issues(
                owner=config.repository_owner,
                repository=config.repository_name,
                duedate_field_name=config.duedate_field_name, # <-- C'era una virgola mancante qui
                task_status_field_name=config.task_status_field_name
            )
    except Exception as e:
        logger.error(f"Errore durante il recupero delle issue: {e}")
        return # Esci se c'è un errore critico
    if not issues:
        logger.info('No issues found')
        return

    for issue in issues:
        if config.is_enterprise:
            projectItem = issue
            issue = issue['content']
        else:
            # ... (logica non enterprise)
            projectNodes = issue['projectItems']['nodes']
            projectItem = next((entry for entry in projectNodes if entry['project']['number'] == config.project_number), None)

        if projectItem is None:
            continue

        # --- CONTROLLO STATUS ---
        # Verifichiamo se l'issue ha uno status tra quelli esclusi
        # Nota: 'statusValue' deve essere restituito dalla tua query in graphql.py
        if 'statusValue' in projectItem and projectItem['statusValue']:
            current_status = projectItem['statusValue'].get('name', '').lower()
            if current_status in excluded_statuses:
                logger.info(f"Salto issue #{issue['number']} perché lo status è '{current_status}'")
                continue

        # --- CONTROLLO DUEDATE ---
        if not projectItem.get('fieldValueByName'):
            continue

        duedate = projectItem["fieldValueByName"]["date"]
        duedate_obj = datetime.strptime(duedate, "%Y-%m-%d").date()

        if duedate_obj - datetime.now().date() > timedelta(days=config.giorni_preavviso):
            continue

        assignees = issue['assignees']['nodes']

        if config.notification_type == 'email':
            # Passiamo il nome del progetto (recuperato dal config) alla funzione di preparazione
            subject, message, to = utils.prepare_expiring_issue_email_message(
                issue=issue,
                assignees=assignees,
                duedate=duedate_obj,
                project_name=getattr(config, 'project_name', 'Project') # <--- PASSO IL NOME
            )

            if not config.dry_run:
                utils.send_email(
                    from_email=config.smtp_from_email,
                    to_email=to,
                    subject=subject,
                    html_body=message
                )
'''


from datetime import datetime, timedelta
from logger import logger
import config
import utils
import graphql

def notify_expiring_issues():
    # 1. Preparazione filtri e variabili iniziali
    # Trasformiamo la stringa "done, closed" in una lista ['done', 'closed']
    excluded_statuses = [s.strip().lower() for s in getattr(config, 'excluded_statuses', "done").split(",") if s]
    issues = []
    
    # 2. Recupero delle issue tramite GraphQL
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
        logger.error(f"Errore critico durante il recupero delle issue: {e}")
        return

    if not issues:
        logger.info('Nessuna issue trovata.')
        return

    # 3. Ciclo di elaborazione e filtraggio
    for item in issues:
        # Gestione diversa della struttura dati tra Enterprise e Repo standard
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
        # Salta se lo status è tra quelli esclusi (es. "done")
        if 'statusValue' in projectItem and projectItem['statusValue']:
            current_status = projectItem['statusValue'].get('name', '').lower()
            if current_status in excluded_statuses:
                logger.info(f"Salto issue #{issue_data['number']} perché lo status è '{current_status}'")
                continue

        # --- FILTRO DATA (DUEDATE) ---
        if not projectItem.get('fieldValueByName') or not projectItem['fieldValueByName'].get('date'):
            continue

        duedate_str = projectItem["fieldValueByName"]["date"]
        duedate_obj = datetime.strptime(duedate_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        
        # Calcolo della differenza (Delta)
        days_until_due = (duedate_obj - today).days

        # Logica: 
        # - Deve essere entro i giorni di preavviso (es. <= 3)
        # - Non deve essere già scaduta da troppo tempo (es. >= 0, o togli se vuoi notificare anche i ritardi)
        if days_until_due > config.giorni_preavviso or days_until_due < 0:
            continue

        # 4. Invio della Notifica
        assignees = issue_data.get('assignees', {}).get('nodes', [])
        
        if config.notification_type == 'email':
            # Nota: Ho usato i tripli apici per la stringa HTML come discusso prima
            subject, message, to = utils.prepare_expiring_issue_email_message(
                issue=issue_data,
                assignees=assignees,
                duedate=duedate_obj,
                project_name=getattr(config, 'project_name', 'Project')
            )

            if not config.dry_run:
                utils.send_email(
                    from_email=config.smtp_from_email,
                    to_email=to,
                    subject=subject,
                    html_body=message
                )
                logger.info(f"Email inviata per issue #{issue_data['number']} a {to}")
            else:
                logger.info(f"[DRY-RUN] Mail pronta per #{issue_data['number']} (scade tra {days_until_due} giorni)")

        elif config.notification_type == 'comment':
            comment = utils.prepare_expiring_issue_comment(
                issue=issue_data,
                assignees=assignees,
                duedate=duedate_obj
            )
            if not config.dry_run:
                graphql.add_issue_comment(issue_data['id'], comment)
                logger.info(f"Commento aggiunto alla issue #{issue_data['number']}")





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
