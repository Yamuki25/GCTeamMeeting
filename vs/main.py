import streamlit as st
import sqlite3
from datetime import datetime, timedelta

############################################
# 1) Konfiguration
############################################

TAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]

# Feste Personenauswahl
PERSONEN = ["Dodi", "Noah", "Juri", "Scoddy", "Jakob", "Johann"]

def generate_halfhour_slots(start_str="12:00", end_str="21:30"):
    fmt = "%H:%M"
    start_dt = datetime.strptime(start_str, fmt)
    end_dt   = datetime.strptime(end_str, fmt)

    slots = []
    current = start_dt
    while current < end_dt:
        slot_start = current
        slot_end   = current + timedelta(minutes=30)
        if slot_end > end_dt:
            break
        label = f"{slot_start.strftime(fmt)}-{slot_end.strftime(fmt)}"
        slots.append(label)
        current = slot_end
    return slots

HALF_HOUR_SLOTS = generate_halfhour_slots("12:00", "21:30")

############################################
# 2) Datenbank-Funktionen (SQLite)
############################################

def init_db():
    conn = sqlite3.connect("verfuegbarkeit.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS verfuegbarkeit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person TEXT,
            tag TEXT,
            slot TEXT
        )
    """)
    conn.commit()
    return conn

def save_availability(conn, person, data_dict):
    """
    data_dict = {
       "Montag": ["12:00-12:30", ...],
       "Dienstag": [...],
       ...
    }
    """
    c = conn.cursor()
    # Alte Einträge entfernen
    c.execute("DELETE FROM verfuegbarkeit WHERE person = ?", (person,))
    # Neue Einträge
    for tag, slots in data_dict.items():
        for slot in slots:
            c.execute("INSERT INTO verfuegbarkeit (person, tag, slot) VALUES (?, ?, ?)",
                      (person, tag, slot))
    conn.commit()

def load_data(conn):
    c = conn.cursor()
    c.execute("SELECT person, tag, slot FROM verfuegbarkeit")
    rows = c.fetchall()

    data = {}
    for person, tag, slot in rows:
        if person not in data:
            data[person] = {t: [] for t in TAGE}
        data[person][tag].append(slot)
    
    # Sortieren pro Tag
    for p in data:
        for t in TAGE:
            data[p][t].sort(key=slot_to_minutes)

    return data

def delete_person(conn, person):
    c = conn.cursor()
    c.execute("DELETE FROM verfuegbarkeit WHERE person = ?", (person,))
    conn.commit()

############################################
# 3) Gemeinsame Slots
############################################

def find_common_slots(selected_data, meeting_length):
    persons = list(selected_data.keys())
    if len(persons) < 2:
        return {}

    common_per_day = {}
    for tag in TAGE:
        # Starte mit Slots der ersten Person
        set_slots = set(selected_data[persons[0]][tag])
        # Schnittmenge mit allen weiteren
        for p in persons[1:]:
            set_slots = set_slots.intersection(selected_data[p][tag])

        halfhour_list = sorted(list(set_slots), key=slot_to_minutes)
        if meeting_length == 30:
            common_per_day[tag] = halfhour_list
        else:
            common_per_day[tag] = find_hour_blocks(halfhour_list)

    return common_per_day

def find_hour_blocks(halfhour_list):
    result = []
    i = 0
    while i < len(halfhour_list) - 1:
        slot_a = halfhour_list[i]
        slot_b = halfhour_list[i+1]
        if slot_to_minutes(slot_b) == slot_to_minutes(slot_a) + 30:
            start_str = slot_a.split("-")[0]
            end_str   = slot_b.split("-")[1]
            hour_label = f"{start_str}-{end_str}"
            result.append(hour_label)
            i += 2
        else:
            i += 1
    return result

def slot_to_minutes(slot_label):
    start_str = slot_label.split("-")[0]
    hh, mm = start_str.split(":")
    return int(hh)*60 + int(mm)

############################################
# 4) Streamlit-App
############################################

def main():
    st.title("GREY CAPITAL Terminfinder")

    conn = init_db()

    st.markdown("""
    **Anleitung**  
    - Wähle deinen Namen.
    - Markiere in der Tabelle per Checkbox deine freien halbstündigen Slots.  
      - Per „Alle“-Button kannst du eine ganze Zeile für alle 5 Wochentage auf einmal setzen.  
    - Klicke auf **Speichern / Aktualisieren**, um deine Daten zu sichern.  
    - Sieh dir unten die Übersicht an und berechne gemeinsame Slots für ausgewählte Personen (30 oder 60 Min).
    """)

    # Session State für Zwischenstände
    if "checkboxes" not in st.session_state:
        st.session_state["checkboxes"] = {}

    # (A) Personenauswahl (Selectbox)
    st.subheader("Verfügbarkeit eintragen")
    person = st.selectbox("Wer bist du?", ["(bitte wählen)"] + PERSONEN)

    # Kopfzeile
    header_cols = st.columns(len(TAGE) + 2)
    header_cols[0].write("**Slot**")
    for i, t in enumerate(TAGE, start=1):
        header_cols[i].write(f"**{t}**")
    header_cols[len(TAGE)+1].write("**Alle**")

    # Tabelle
    for slot_label in HALF_HOUR_SLOTS:
        row_cols = st.columns(len(TAGE) + 2)
        row_cols[0].write(slot_label)

        # Checkboxen Mo–Fr
        for i, tag in enumerate(TAGE, start=1):
            key = f"{slot_label}::{tag}"
            current_val = st.session_state["checkboxes"].get(key, False)
            new_val = row_cols[i].checkbox("", value=current_val, key=key)
            st.session_state["checkboxes"][key] = new_val

        # Button "Alle"
        btn_key = f"all-{slot_label}"
        if row_cols[len(TAGE)+1].button("Alle", key=btn_key):
            for t in TAGE:
                k = f"{slot_label}::{t}"
                st.session_state["checkboxes"][k] = True
            st.rerun()

    if st.button("Speichern / Aktualisieren"):
        if person == "(bitte wählen)":
            st.warning("Bitte eine Person auswählen!")
        else:
            # Bauen dict: {"Montag": [...], "Dienstag": [...], ...}
            person_data = {t: [] for t in TAGE}
            for (key, val) in st.session_state["checkboxes"].items():
                if val:
                    slot_str, tag_str = key.split("::")
                    person_data[tag_str].append(slot_str)
            # In DB speichern
            save_availability(conn, person, person_data)
            st.success(f"Verfügbarkeiten für {person} gespeichert!")

    # Übersicht
    st.write("---")
    st.subheader("Übersicht aller Personen")
    data = load_data(conn)
    if not data:
        st.info("Noch keine Einträge vorhanden.")
    else:
        for p, tage_data in data.items():
            st.write(f"### {p}")
            for t in TAGE:
                slots = tage_data[t]
                if slots:
                    st.write(f"- **{t}**: {', '.join(slots)}")
                else:
                    st.write(f"- **{t}**: (nichts)")

            if st.button(f"Lösche Einträge von {p}"):
                delete_person(conn, p)
                st.warning(f"Einträge von {p} wurden gelöscht!")
                st.rerun()

    # Gemeinsame Slots
    st.write("---")
    st.subheader("Gemeinsame freie Zeitblöcke (Personenauswahl)")

    # Schau, ob es min. 2 Personen gibt
    if len(data.keys()) < 2:
        st.info("Mindestens 2 Personen eingetragen haben, um Schnittmengen zu sehen.")
    else:
        # Multi-Select nur aus vorhandenen (nicht zwingend 6)
        all_in_db = list(data.keys())  # nur die, die schon was haben
        selected_persons = st.multiselect(
            "Wähle die Personen, deren gemeinsame Slots du möchtest:",
            all_in_db,
            default=all_in_db
        )
        meet_choice = st.radio("Meetingdauer:", ["30 Minuten", "60 Minuten"])
        meet_len = 30 if meet_choice == "30 Minuten" else 60

        if st.button("Schnittmengen anzeigen"):
            if len(selected_persons) < 2:
                st.warning("Bitte mind. 2 Personen auswählen.")
            else:
                subset = {p: data[p] for p in selected_persons}
                common = find_common_slots(subset, meeting_length=meet_len)

                any_found = False
                for t in TAGE:
                    slots = common.get(t, [])
                    if slots:
                        any_found = True
                        st.write(f"**{t}**: {', '.join(slots)}")
                    else:
                        st.write(f"**{t}**: Keine gemeinsamen Slots")
                if not any_found:
                    st.info("Keine gemeinsamen Zeitfenster gefunden.")


if __name__ == "__main__":
    main()