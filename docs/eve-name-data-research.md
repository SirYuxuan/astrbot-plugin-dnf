# EVE Online item-name data — research/proposal only

Checked **2026-09-11**. Scope: CCP's **Tranquility** SDE, item type IDs, English/Chinese names, and refresh strategy. No implementation; pricing/ESI market behavior is outside this sidecar.

## Verified source facts

- **Current formats: ZIP archives containing JSON Lines or YAML.** For integer-keyed datasets JSONL records carry the integer in `_key`; `_value` is used when the value is not an object. YAML supports integer keys directly. CCP warns that large YAML datasets can be slow/memory-intensive. Source: [official SDE documentation](https://developers.eveonline.com/docs/services/static-data/).
- **Latest build observed: `3503375`, released `2026-09-10T11:09:04Z`.** Both the live manifest's `sde` record and the archive's `_sde.jsonl` agreed. This is a dated observation, not a permanently latest build. Sources: [live manifest](https://developers.eveonline.com/static-data/tranquility/latest.jsonl), [exact inspected JSONL archive](https://developers.eveonline.com/static-data/tranquility/eve-online-static-data-3503375-jsonl.zip).
- **Names and IDs are together in `types.jsonl`.** The record `_key` is the item type ID; `name` is a locale-keyed object, including `name.en` and, where present, `name.zh`. Records also carry fields such as `groupID`, `marketGroupID`, and `published`. `translationLanguages.jsonl` explicitly lists `en: English` and **`zh: Chinese`**, alongside de/es/fr/ja/ko/ru. This was checked in CCP's actual **Tranquility** archive, not inferred from Serenity data or ESI language parameters. Source: [inspected archive](https://developers.eveonline.com/static-data/tranquility/eve-online-static-data-3503375-jsonl.zip), members `types.jsonl` and `translationLanguages.jsonl`.

Directly observed examples from that archive:

| Type ID (`_key`) | `name.en` | `name.zh` |
| --- | --- | --- |
| 34 | Tritanium | 三钛合金 |
| 35 | Pyerite | 类晶体胶矿 |
| 587 | Rifter | 裂谷级 |
| 44992 | PLEX | 伊甸币 |

Source for all examples: [CCP build 3503375](https://developers.eveonline.com/static-data/tranquility/eve-online-static-data-3503375-jsonl.zip), `types.jsonl`. The PLEX row establishes identity/name only, not pricing semantics.

### Localization coverage: measured, not guaranteed

A full scan of `types.jsonl` in that exact archive found **52,999 records**: all had nonempty English names; **52,585 had Chinese names**, leaving **414 missing/empty `zh` names**. Among **27,116 records with `published: true`**, **127 lacked nonempty Chinese names**. These are locally computed counts over the official source, not CCP completeness guarantees. “Published” is the source field, not proof of current market availability. Source: [same archive](https://developers.eveonline.com/static-data/tranquility/eve-online-static-data-3503375-jsonl.zip).

**Not verified / do not assume:** every item will have Chinese; `zh` guarantees a particular regional/script variant (the language table only calls it “Chinese”); translations exactly match every live client's current wording; Chinese SDE availability implies ESI accepts `language=zh`; names are unique; or IDs have a documented never-reuse guarantee. No separate `zh-CN`/`zh-TW` language keys were observed in the inspected type-name maps. Do not substitute Serenity IDs/data or machine translations while presenting them as official Tranquility names.

## Verified update interface

- Poll [latest.jsonl](https://developers.eveonline.com/static-data/tranquility/latest.jsonl), selecting the record with `_key == "sde"`. Download the pinned URL `https://developers.eveonline.com/static-data/tranquility/eve-online-static-data-<build-number>-<variant>.zip`, with `variant` `jsonl` or `yaml`. Convenience [latest JSONL](https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip) and [latest YAML](https://developers.eveonline.com/static-data/eve-online-static-data-latest-yaml.zip) URLs redirect to the current build. Source: [official automation documentation](https://developers.eveonline.com/docs/services/static-data/#automation).
- Per-build changes are at `https://developers.eveonline.com/static-data/tranquility/changes/<build-number>.jsonl`; `_meta.lastBuildNumber` identifies the prior SDE. The [observed change file](https://developers.eveonline.com/static-data/tranquility/changes/3503375.jsonl) names previous build `3500372` and lists added/changed keys for `militaryCampaignObjectives`, with no `types` entry. That file provides changed keys, not replacement item records. Sources: that file and [official docs](https://developers.eveonline.com/docs/services/static-data/#automation).
- CCP documents ETag/Last-Modified support and five-minute caching of non-static resources. Schema changes have a separate [official changelog](https://developers.eveonline.com/static-data/tranquility/schema-changelog.yaml); it includes changes to `types` as recently as August 2026. Sources: [HTTP caching docs](https://developers.eveonline.com/docs/services/static-data/#http-caching), schema changelog. Do not design against an old export layout without checking the new archive.

## Proposal (engineering recommendations, not CCP requirements)

1. Use the **official Tranquility JSONL SDE** as a local bilingual name-to-type-ID catalog. Store canonical numeric type ID plus English, nullable Chinese, publication/group metadata, and SDE build provenance. Keep names as labels/search keys, never identity keys.
2. Index both official names; keep any user/community aliases separate and explicitly labeled. Resolve duplicate/ambiguous matches with candidate type IDs instead of silently selecting one. For Chinese display use `name.zh`, then `name.en`, then the numeric ID; do not invent translations.
3. Bootstrap from a pinned build; check the manifest conditionally at startup and, for example, daily. Download only on build change. Preserve the last good index during fetch/parse failures; validate required fields, ID uniqueness, and localization counts before atomically replacing it. These frequencies/validation rules are proposed policy.
4. Initially rebuild the small derived name index from the full new archive rather than implementing incremental patching. Change metadata can later avoid unnecessary rebuilds, but follow the complete `lastBuildNumber` chain across skipped releases; if the chain is unavailable or uncertain, rebuild. Check schema changes and tolerate unrelated added fields. Record checked-at time and active build for diagnostics.

Method: official developer documentation/manifests were fetched directly; ZIP members were inspected in memory via HTTP range requests, with every type-name record counted. Only this Markdown file was written; no downloaded archives or feature code were saved.
