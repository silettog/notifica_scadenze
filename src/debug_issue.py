import config
import graphql
from datetime import datetime
from logger import logger

def debug_issue_48():
    logger.info("--- INIZIO DEBUG ISSUE #48 ---")
    
    # 1. Recupero dati
    try:
        # Recuperiamo le issue (usiamo il metodo enterprise visto il tuo workflow)
        issues = graphql.get_project_issues(
            owner=config.repository_owner,
            owner_type=config.repository_owner_type,
            project_number=config.project_number,
            duedate_field_name=config.duedate_field_name,
            task_status_field_name=config.task_status_field_name,
            filters={'open_only': False} # Vediamo anche se è chiusa
        )
    except Exception as e:
        logger.error(f"Errore nel recupero dati: {e}")
        return

    # Cerchiamo la 48
    item = next((i for i in issues if i.get('content', {}).get('number') == 48), None)

    if not item:
        logger.error("ERRORE: La issue #48 non è stata trovata nei primi 100 risultati del progetto!")
        return

    issue_data = item['content']
    logger.info(f"Trovata Issue #{issue_data['number']}: '{issue_data['title']}'")

    # 2. Controllo Stato
    status_val = item.get('statusValue')
    current_status = status_val.get('name', 'NON DEFINITO') if status_val else 'NON DEFINITO'
    excluded = [s.strip().lower() for s in config.excluded_statuses.split(",")]
    
    logger.info(f"STATO ATTUALE: '{current_status}'")
    if current_status.lower() in excluded:
        logger.warning(f"Sospetto: Lo stato '{current_status}' è tra quelli ESCLUSI ({excluded})")
    else:
        logger.info(f"Stato OK: '{current_status}' non è tra gli esclusi.")

    # 3. Controllo Data
    date_field = item.get('fieldValueByName')
    if not date_field or not date_field.get('date'):
        logger.error(f"ERRORE DATA: Il campo '{config.duedate_field_name}' è VUOTO per questa issue.")
    else:
        duedate_str = date_field['date']
        logger.info(f"DATA TROVATA: {duedate_str}")
        try:
            duedate_obj = datetime.strptime(duedate_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            diff = (duedate_obj - today).days
            logger.info(f"CALCOLO: Scadenza tra {diff} giorni (se negativo è ritardo)")
        except Exception as e:
            logger.error(f"ERRORE FORMATO DATA: GitHub ha restituito '{duedate_str}', ma il codice si aspetta YYYY-MM-DD. Errore: {e}")

    # 4. Controllo Email
    assignees = issue_data.get('assignees', {}).get('nodes', [])
    if not assignees:
        logger.warning("ATTENZIONE: Nessun assegnatario trovato per questa issue.")
    else:
        for a in assignees:
            email = a.get('email')
            login = a.get('login')
            if email:
                logger.info(f"EMAIL TROVATA: L'utente {login} ha email pubblica: {email}")
            else:
                logger.error(f"EMAIL MANCANTE: L'utente {login} NON ha l'email pubblica su GitHub. Lo script non saprebbe a chi scrivere.")

    logger.info("--- FINE DEBUG ---")

if __name__ == "__main__":
    debug_issue_48()
