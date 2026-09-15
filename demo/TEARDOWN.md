# Teardown

Everything this demo creates lives in three places: two BigQuery datasets, one GCS
prefix, and one BigQuery connection. Removing them is quick, but the order matters
slightly and one of the steps is easy to forget.

> [!CAUTION]
> These commands delete data permanently and without confirmation. Read the project
> and dataset names before you press enter — `bq rm -r -f` does not ask twice.

Load your own values first:

```bash
cd demo
source config.env
```

## 1 · Datasets

```bash
bq rm -r -f --project_id="${CDP_PROJECT}" "${CDP_DS}"
bq rm -r -f --project_id="${CDP_PROJECT}" "${CDP_DS_TRUTH}"
```

This removes the tables, views, table functions, the BQML model, the stored
procedure, the vector indexes and the search index in one go.

> [!NOTE]
> `person_crosswalk` and `adjudications` go with them. Both are deliberately
> append-only and survive `run.sh`; if you want to reset identifier assignment or
> force re-adjudication *without* a full teardown, drop just those two tables and
> re-run from stage 60.

## 2 · Storage

```bash
gcloud storage rm --recursive "gs://${CDP_BUCKET}/raw" \
                "gs://${CDP_BUCKET}/pos" \
                "gs://${CDP_BUCKET}/support" \
                "gs://${CDP_BUCKET}/enrich" \
                "gs://${CDP_BUCKET}/call_transcripts" \
                "gs://${CDP_BUCKET}/truth"
```

Or, if `setup.sh` created the bucket for you and nothing else uses it:

```bash
gcloud storage rm --recursive "gs://${CDP_BUCKET}"
```

## 3 · The connection — the one people forget

```bash
bq rm --connection \
  --project_id="${CDP_PROJECT}" \
  --location="${CDP_LOCATION}" \
  "${CDP_CONNECTION}"
```

Its service account may also hold `roles/aiplatform.user` at project level, granted
during setup. Connections are free, so leaving one behind costs nothing — but an
orphaned service account with Vertex AI access is the kind of thing that turns up in
a security review months later, attached to a demo nobody remembers running.

```bash
gcloud projects get-iam-policy "${CDP_PROJECT}" \
  --flatten="bindings[].members" \
  --filter="bindings.role:roles/aiplatform.user" \
  --format="table(bindings.members)"
```

Remove the binding for the connection's service account if it is no longer needed.

## 4 · Local

```bash
rm -rf data .rendered .state config.env
```

`data/` is regenerable from `CDP_SEED` — the same seed produces byte-identical files,
so deleting it loses nothing.

## What is safe to keep

Nothing here is expensive at rest once the datasets are gone. If you expect to run the
demo again, keeping the bucket and the connection saves the two slowest parts of
`setup.sh`; keeping `config.env` saves answering the prompts.
