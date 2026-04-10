from datetime import datetime, timedelta
from logger import logger
import config
import utils
import graphql

"""
def notify_expiring_issues():
    if config.is_enterprise:
        # Get the issues
        issues = graphql.get_project_issues(
            owner=config.repository_owner,
            owner_type=config.repository_owner_type,
            project_number=config.project_number,
            duedate_field_name=config.duedate_field_name,
            #task_status_field_name=config.task_status_field_name,
            filters={'open_only': True}
        )
    else:
        # Get the issues
        issues = graphql.get_repo_issues(
            owner=config.repository_owner,
            repository=config.repository_name,
            duedate_field_name=config.duedate_field_name
            #task_status_field_name=config.task_status_field_name
        )

    # Check if there are issues available
    if not issues:
        logger.info('No issues has been found')
        return

    # Get the date for tomorrow
    #tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow = datetime.now().date() + timedelta(days=config.giorni_preavviso)

    # Loop through issues
    for issue in issues:
        if config.is_enterprise:
            projectItem = issue
            issue = issue['content']
        else:
            projectNodes = issue['projectItems']['nodes']

            # If no project is assigned to the
            if not projectNodes:
                continue

            # Check if the desire project is assigned to the issue
            projectItem = next((entry for entry in projectNodes if entry['project']['number'] == config.project_number),
                               None)

        # Usa una protezione:
        if projectItem is None or 'fieldValueByName' not in projectItem:
            print("Salto un elemento vuoto o non valido...")
            continue
            
        # The fieldValueByName contains the date for the DueDate Field
        if not projectItem['fieldValueByName']:
            continue

        # Get the duedate value and convert it to date object
        duedate = projectItem["fieldValueByName"]["date"]
        duedate_obj = datetime.strptime(duedate, "%Y-%m-%d").date()

        # Check if the project item is due soon or not
        ####################################################################
        logger.info(f' ***** {projectNodes} ')
        #pippo=issue['projectItems']['nodes']['project']['title']
        #logger.info(f' ***** PROGETTO: {pippo}')
        logger.info(f' ***** Data consegna-duedate: {duedate_obj}')
        logger.info(f' ***** Intervallo preavviso: {config.giorni_preavviso}')
        logger.info(f' ***** Intervallo preavviso: {timedelta(days=config.giorni_preavviso)}')
        logger.info(f' ***** Data di oggi: {datetime.now().date()}')
        logger.info(f' ***** Delta-time: {duedate_obj - datetime.now().date()}')
        #####################################################################
        if duedate_obj - datetime.now().date() > timedelta(days=config.giorni_preavviso):
        #if duedate_obj != tomorrow:
            continue

        # Get the list of assignees
        assignees = issue['assignees']['nodes']

        # Handle notification type
        if config.notification_type == 'comment':
            # Prepare the notification content
            comment = utils.prepare_expiring_issue_comment(
                issue=issue,
                assignees=assignees,
                duedate=duedate_obj
            )
            if not config.dry_run:
                # Add the comment to the issue
                graphql.add_issue_comment(issue['id'], comment)

            logger.info(f'Comment added to issue #{issue["number"]} ({issue["id"]}) with due date on {duedate_obj}')
        elif config.notification_type == 'email':
            subject, message, to = utils.prepare_expiring_issue_email_message(
                issue=issue,
                assignees=assignees,
                duedate=duedate_obj,
            )

            if not config.dry_run:
                # Send the email
                utils.send_email(
                    from_email=config.smtp_from_email,
                    to_email=to,
                    subject=subject,
                    html_body=message
                )

            logger.info(f'Email sent to {to} for issue #{issue["number"]} with due date on {duedate_obj}')
"""

def notify_expiring_issues():
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
