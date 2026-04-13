# Obsidian Setup

## Open this workspace as a vault

In Obsidian:
1. Choose **Open folder as vault**
2. Select `/home/asurani/.openclaw/workspace`

## Recommended plugins

- Dataview
- Templater

## Recommended settings

- Daily notes folder: `memory/`
- Templater templates folder: `templates/`
- Attachments folder: `attachments/` or leave default

## Suggested templates

- Daily memory note: `templates/daily-memory-note.md`
- Journal note: `templates/journal-note.md`
- Concept note: `templates/concept-note.md`

## Useful starter queries

### Recent memory files

```dataview
LIST FROM "memory" SORT file.name DESC LIMIT 7
```

### Recent journal entries

```dataview
LIST FROM "second-brain/journal" SORT file.name DESC LIMIT 7
```

### Concept notes

```dataview
LIST FROM "second-brain/concepts" SORT file.name ASC
```

## Graph tips

Use wiki-links like `[[MEMORY]]`, `[[USER]]`, `[[SOUL]]`, and links between concept notes to make the graph useful.

## Related

- [[HOME]]
- [[MEMORY]]
- [[OpenClaw Memory System]]
- [[memory-maintenance]]
- [[Memory Dashboard]]
- [[Journal Dashboard]]
- [[Concept Dashboard]]
