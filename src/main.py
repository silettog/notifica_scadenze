from datetime import datetime
from collections import defaultdict
from logger import logger
import config
import utils
import github_api as graphql

def notify_expiring_issues():
    """
    Gestisce le notifiche di scadenza e rileva incongruenze di stato.
    Invia anche un report integrale ai supervisori.
    """
    excluded_statuses = [s.strip().lower() for s in getattr(config, 'excluded_statuses', "").split(",") if s.strip()]
    notifications_map = defaultdict(list)
    full_project_list = [] # Per il report integrale
    extra_emails = [e.strip() for e in getattr(config, 'mail_aggiuntive', '').split(',') if e.strip()]
    
    try:
        # Recuperiamo TUTTO (open_only: False) per avere il quadro completo
        issues = graphql.get_project_issues(
            owner=config.repository_owner,
            owner_type=config.repository_owner_type,
            project_number=config.project_number,
            duedate_field_name=config.duedate_field_name,
            task_status_field_name=config.task_status_field_name,
            filters={'open_only': False} 
        )
    except Exception as e:
        logger.error(f"Errore API: {e}")
        return

    if not issues:
        logger.warning("Nessuna issue trovata.")
        return

    for item in issues:
        try:
            issue_data = item.get('content', {})
            if not issue_data or issue_data.get('__typename') == 'DraftIssue':
                continue

            num = issue_data.get('number')
            title = issue_data.get('title')
            state = issue_data.get('state', 'UNKNOWN') # OPEN o CLOSED
            
            status_obj = item.get('statusValue')
            current_status = status_obj.get('name', 'N/A') if status_obj else 'N/A'
            
            date_field = item.get('fieldValueByName')
            date_val = date_field.get('date') if date_field else None

            # --- LOGICA ANOMALIA STATO ---
            is_in_excluded = current_status.lower() in excluded_statuses
            anomaly_msg = ""
            if state == 'CLOSED' and not is_in_excluded:
                anomaly_msg = f"⚠️ INCONGRUENZA: Chiusa ma in colonna '{current_status}'"
            elif state == 'OPEN' and is_in_excluded:
                anomaly_msg = f"⚠️ INCONGRUENZA: In colonna finale ma ancora Aperta"

            # --- DATA PER REPORT INTEGRALE (Solo mail_aggiuntive) ---
            full_project_list.append({
                'number': num,
                'title': title,
                'status': current_status,
                'state': state,
                'duedate': date_val or 'N.D.',
                'anomaly': anomaly_msg
            })

            # --- FILTRO PER NOTIFICHE SCADENZA (Solo se OPEN) ---
            if state == 'OPEN' and not is_in_excluded and date_val:
                duedate_obj = datetime.strptime(date_val, "%Y-%m-%d").date()
                days_diff = (duedate_obj - datetime.now().date()).days
                
                msg_type = None
                label_ritardo = ""
                if 0 <= days_diff <= config.giorni_preavviso:
                    msg_type = "IN SCADENZA"
                elif days_diff < 0:
                    msg_type = "SCADUTA"
                    label_ritardo = f"{abs(days_diff)} giorni"

                if msg_type:
                    issue_info = {
                        'number': num,
                        'title': title,
                        'url': issue_data.get('url'),
                        'duedate': duedate_obj,
                        'type': msg_type,
                        'delay': label_ritardo,
                        'anomaly': anomaly_msg
                    }
                    
                    assignees = issue_data.get('assignees', {}).get('nodes', [])
                    recipients = set([a['email'] for a in assignees if a.get('email')] + extra_emails)
                    for email in recipients:
                        notifications_map[email].append(issue_info)

        except Exception as e:
            logger.error(f"Errore su issue #{item.get('content',{}).get('number')}: {e}")

    # 1. Invio email di notifica scadenze (Assegnatari + Extra)
    if notifications_map:
        send_aggregated_emails(notifications_map, "Notifica Scadenze")
    
    # 2. Invio Report Integrale (Solo a mail_aggiuntive)
    if extra_emails and full_project_list:
        send_full_summary_email(extra_emails, full_project_list)


def send_full_summary_email(to_emails, issue_list):
    """
    Invia un report completo di tutte le issue del progetto.
    """
    subject = f"📊 Report Integrale Progetto: {getattr(config, 'project_name', 'GitHub')}"
    
    rows = ""
    for i in issue_list:
        # Colore riga se c'è un'anomalia
        bg_style = "background-color: #fff4f4;" if i['anomaly'] else ""
        rows += f"""
            <tr style='{bg_style}'>
                <td style='padding:8px; border:1px solid #ddd;'>#{i['number']}</td>
                <td style='padding:8px; border:1px solid #ddd;'>{i['title']}</td>
                <td style='padding:8px; border:1px solid #ddd;'>{i['status']} ({i['state']})</td>
                <td style='padding:8px; border:1px solid #ddd;'>{i['duedate']}</td>
                <td style='padding:8px; border:1px solid #ddd; color:red; font-size:11px;'>{i['anomaly']}</td>
            </tr>
        """

    html = f"""
    <html>
    <body style='font-family:sans-serif;'>
        <h3>📊 Stato Completo Progetto: {getattr(config, 'project_name', 'PTE IGR')}</h3>
        <p>Questo report contiene l'elenco di tutte le issue associate al progetto.</p>
        <table style='width:100%; border-collapse:collapse; font-size:13px;'>
            <thead>
                <tr style='background:#f2f2f2;'>
                    <th>ID</th><th>Titolo</th><th>Status (Core State)</th><th>Scadenza</th><th>Note</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </body>
    </html>
    """
    if not config.dry_run:
        utils.send_email(config.smtp_from_email, to_emails, subject, html)
        logger.info(f"Report integrale inviato a {to_emails}")


def send_aggregated_emails(notifications_map, subject_prefix):
    """
    Invia le notifiche di scadenza.
    """
    for email, items in notifications_map.items():
        subject = f"{subject_prefix} ({len(items)} attività)"
        html_rows = ""
        for i in items:
            color = "#D32F2F" if i['type'] == 'SCADUTA' else "#F57C00"
            anomaly_tag = f"<br><span style='color:red; font-size:11px;'>{i['anomaly']}</span>" if i['anomaly'] else ""
            
            html_rows += f"""
                <tr>
                    <td style='padding:10px; border-bottom:1px solid #ddd;'>
                        <b style='color:{color};'>[{i['type']}]</b> #{i['number']} - {i['title']}{anomaly_tag}<br>
                        <small>Data prevista: {i['duedate']} {f' - Ritardo: {i["delay"]}' if i['delay'] else ''}</small>
                    </td>
                    <td style='padding:10px; border-bottom:1px solid #ddd; text-align:right;'>
                        <a href='{i['url']}' style='background:#0366d6; color:white; padding:5px; text-decoration:none; border-radius:3px;'>Apri</a>
                    </td>
                </tr>
            """

        full_html = f"<html><body><table style='width:100%; border-collapse:collapse;'>{html_rows}</table></body></html>"
        if not config.dry_run:
            utils.send_email(config.smtp_from_email, [email], subject, full_html)
