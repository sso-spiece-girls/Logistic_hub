"""Remove capienza from SlotOrario - capacity is only per-warehouse now."""

# 1. models.py - remove capienza column
with open('logistic_hub/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = "    capienza = db.Column(db.Integer, nullable=False, default=1)\n"
assert old in content, "models.py: capienza line not found!"
content = content.replace(old, '')  # just remove the line

with open('logistic_hub/models.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print('OK: models.py - capienza rimosso da SlotOrario')


# 2. forms.py - remove capienza from SlotOrarioForm
with open('logistic_hub/forms.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = "    capienza = IntegerField(\"Capienza massima\", validators=[DataRequired()], default=1)\n"
assert old in content, "forms.py: capienza line not found!"
content = content.replace(old, '')

with open('logistic_hub/forms.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print('OK: forms.py - capienza rimosso da SlotOrarioForm')


# 3. prenotazioni.py - remove _capienza_magazzini() function and capienza refs
with open('logistic_hub/routes/prenotazioni.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove _capienza_magazzini() function
old_func = '''def _capienza_magazzini():
    """Restituisce capienza totale sommando tutti i magazzini configurati, o 999 se nessuno."""
    righe = MagazzinoCapienza.query.all()
    if not righe:
        return 999
    return sum(r.capienza_contemporanea for r in righe)


'''
assert old_func in content, "prenotazioni.py: _capienza_magazzini() not found!"
content = content.replace(old_func, '')
print('OK: prenotazioni.py - _capienza_magazzini() rimossa')

# Remove capienza= from admin_slot_nuovo
old = "            capienza=form.capienza.data,\n"
assert old in content, "prenotazioni.py: capienza in admin_slot_nuovo not found!"
content = content.replace(old, '')
print('OK: prenotazioni.py - capienza rimossa da admin_slot_nuovo')

# Remove regola.capienza = from admin_slot_modifica
old = "        regola.capienza = form.capienza.data\n"
assert old in content, "prenotazioni.py: regola.capienza in admin_slot_modifica not found!"
content = content.replace(old, '')
print('OK: prenotazioni.py - capienza rimossa da admin_slot_modifica')

with open('logistic_hub/routes/prenotazioni.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)


# 4. admin_slot.html - remove capienza column header and cell
with open('logistic_hub/templates/prenotazioni/admin_slot.html', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''                <th>Capienza</th>
'''
assert old in content, "admin_slot.html: Capienza header not found!"
content = content.replace(old, '')

old = '''                <td>{{ r.capienza }}</td>
'''
assert old in content, "admin_slot.html: Capienza cell not found!"
content = content.replace(old, '')

with open('logistic_hub/templates/prenotazioni/admin_slot.html', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print('OK: admin_slot.html - capienza rimossa')


# 5. admin_slot_form.html - remove capienza form field
with open('logistic_hub/templates/prenotazioni/admin_slot_form.html', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''            <div class="form-group">
                {{ form.capienza.label(class="form-label") }}
                {{ form.capienza(class="form-input", type="number", min=1) }}
                {% for error in form.capienza.errors %}<span class="form-error">{{ error }}</span>{% endfor %}
            </div>
'''
assert old in content, "admin_slot_form.html: capienza form field not found!"
content = content.replace(old, '')

with open('logistic_hub/templates/prenotazioni/admin_slot_form.html', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print('OK: admin_slot_form.html - capienza rimossa')


# 6. Remove the capienza from the form-row wrapper if it's now empty
# The form-row wraps durata_minuti and capienza. Now only durata_minuti remains.
# We need to remove the outer form-row div.
# Current state after removing capienza:
# <div class="form-row">
#     <div class="form-group">
#         {{ form.durata_minuti.label(...) }}
#         {{ form.durata_minuti(...) }}
#         ...
#     </div>
# </div>
# -> Simplify to just the form-group without the row wrapper.
with open('logistic_hub/templates/prenotazioni/admin_slot_form.html', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''        <div class="form-row">
            <div class="form-group">
                {{ form.durata_minuti.label(class="form-label") }}
                {{ form.durata_minuti(class="form-input", type="number", min=15, step=15) }}
                {% for error in form.durata_minuti.errors %}<span class="form-error">{{ error }}</span>{% endfor %}
            </div>
        </div>'''
new = '''        <div class="form-group">
            {{ form.durata_minuti.label(class="form-label") }}
            {{ form.durata_minuti(class="form-input", type="number", min=15, step=15) }}
            {% for error in form.durata_minuti.errors %}<span class="form-error">{{ error }}</span>{% endfor %}
        </div>'''
assert old in content, "admin_slot_form.html: durata_minuti in form-row not found!"
content = content.replace(old, new)

with open('logistic_hub/templates/prenotazioni/admin_slot_form.html', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print('OK: admin_slot_form.html - form-row semplificata')


# 7. main.py - add migration DROP COLUMN + remove capienza from seed
with open('logistic_hub/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add migration step before "SQLite" comment
old_migrate = '''    # SQLite: l'auto-index per unique=True si chiama sqlite_autoindex_users_2
    try:
        db.session.execute(text("DROP INDEX IF EXISTS sqlite_autoindex_users_2"))
        db.session.commit()
    except Exception:
        db.session.rollback()'''

new_migrate = '''    # SQLite: l'auto-index per unique=True si chiama sqlite_autoindex_users_2
    try:
        db.session.execute(text("DROP INDEX IF EXISTS sqlite_autoindex_users_2"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    # Rimuove la colonna capienza da slot_orari (ora solo MagazzinoCapienza)
    try:
        db.session.execute(text("ALTER TABLE slot_orari DROP COLUMN IF EXISTS capienza"))
        db.session.commit()
    except Exception:
        db.session.rollback()'''

assert old_migrate in content, "main.py: migration SQLite block not found!"
content = content.replace(old_migrate, new_migrate)
print('OK: main.py - migrazione DROP COLUMN capienza aggiunta')

# Remove capienza=1 from seed
with open('logistic_hub/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_seed = "                durata_minuti=60, capienza=1, attivo=True, creato_da_id=admin_id,"
new_seed = "                durata_minuti=60, attivo=True, creato_da_id=admin_id,"
assert old_seed in content, "main.py: seed capienza not found!"
content = content.replace(old_seed, new_seed)
print('OK: main.py - capienza=1 rimosso da _seed_slot_orari')

with open('logistic_hub/main.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)


print('\n=== TUTTI I CAMBIAMENTI APPLICATI ===')
