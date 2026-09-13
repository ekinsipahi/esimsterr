# The legal system, and how to change it

Legal text lives in `apps/legal/` as data, not as templates. Three files decide
everything:

| File | What it holds |
|---|---|
| `apps/legal/text/*.py` | The sentences. One module per document family. |
| `apps/legal/documents.py` | Which clauses make up which document, and its version. |
| `apps/legal/versions.lock.json` | A hash of every document's text, checked in. |

## Why it is built this way

**Clauses, not pages.** A clause declares the surfaces it applies to. "Purchases
are made on the website" is a footnote on the web and a compliance statement
inside an iOS app; composing one document per surface from a shared library is
what stops the privacy policy and the App Store data disclosure drifting apart.
Forking the documents per platform is how that drift starts.

**Versions, not dates.** Every document carries `version` and `effective`. The
old pages printed `{% now %}`, so they claimed to have been revised today, every
day — which tells a reader nothing and a regulator less.

**A lock file.** `LegalAcceptance` stores `2026.1+082008e03d5425f4`: the version
and a hash of the actual text. If the text could change without the version
changing, every record already written would be a claim about wording the
customer may never have seen. `check_legal` runs in `build.sh` and fails the
deploy if they drift.

## Writing a clause

```python
Clause("fair-use", _("Fair use on unlimited plans"), (
    P(_("\"Unlimited\" means there is no cap that stops you. [[doc:terms|The terms]] "
        "explain the rest, and {site} never bills overage.")),
    UL(_("point one"), _("point two")),
    Callout(_("The sentence people miss and then dispute.")),
    Table((_("Column"),), [(_("cell"),)]),
), surfaces=APP_SURFACES)
```

Blocks: `P`, `H`, `UL`, `OL`, `Callout`, `Table`. Everything is escaped on
render; only these tokens survive:

| Token | Becomes |
|---|---|
| `[[doc:refund]]` | link to a legal document, labelled with its own title |
| `[[doc:refund\|refund terms]]` | the same, with your label |
| `[[url:compatible_devices\|compatibility page]]` | a named Django URL |
| `[[mail]]` | the support address as a `mailto:` |
| `**text**` | bold |
| `{site}` `{company}` `{support}` `{host}` `{jurisdiction}` `{courts}` | settings |

`_` is `gettext_noop`: the strings still land in the `.po` files, but the value
kept in memory is the English source, so the version hash does not change when a
translation does. Avoid literal `{` and `}` in legal text — the substitution
runs over the whole sentence.

## Changing a document

1. Edit the clause.
2. Bump `Document.version` and set a new `effective` date in `documents.py`.
3. Add an entry to `apps/legal/history.py`, and set `material` honestly —
   `True` is what obliges you to email subscribers before their next renewal.
4. `python manage.py check_legal --write`, and commit the lock file.
5. If the change is material, send the notice. Nothing automates that, on
   purpose: deciding that a change matters is a judgement, not a diff.

`check_legal` fails when text moved without a version bump, when a version moved
without a new effective date, when a published document disappears, or when a
version has no entry in the history.

## Adding a document

A module in `apps/legal/text/`, a `Document(...)` in `documents.py`, a route in
`apps/legal/urls.py`, a line in `core/sitemaps.py`, and a footer link. Add it to
`CONTRACT_DOCUMENTS` only if buyers should be recorded as accepting it — that
list is what `record_acceptance()` writes.

## Where acceptance is recorded

| Moment | Context |
|---|---|
| Web sign-up | `signup` |
| Checkout, guest or signed in | `checkout` |
| Subscription checkout | `subscribe` |
| API registration, and `POST /api/v1/legal/accept/` | `signup` / `app` |

Writing a row never raises: an audit row that fails must not be able to stop a
sale. It logs instead.

## Previewing the app wording

Staff can append `?surface=ios` or `?surface=android` to any legal page. Nobody
else can, so the public page can never differ from the one that was indexed.
The app reads `GET /api/v1/legal/<slug>/` with `X-Client-Platform`.
