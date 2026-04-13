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
- Attachments folder: `attachments/` or leave default

## Useful starter queries

### Recent memory files

```dataview
LIST FROM "memory" SORT file.name DESC LIMIT 7
```

### Recent journal entries

```dataview
LIST FROM "second-brain/journal" SORT file.name DESC LIMIT 7
```

## Graph tips

Use wiki-links like `[[MEMORY]]`, `[[USER]]`, `[[SOUL]]`, and links between concept notes to make the graph useful.
