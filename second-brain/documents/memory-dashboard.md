# Memory Dashboard

## Recent daily memory files

```dataview
TABLE file.name AS Date, file.mtime AS Updated
FROM "memory"
SORT file.name DESC
LIMIT 14
```

## Recent files mentioning memory

```dataview
LIST
FROM ""
WHERE contains(file.name, "memory") OR contains(file.path, "memory")
SORT file.mtime DESC
LIMIT 20
```

## Related

- [[HOME]]
- [[MEMORY]]
- [[OpenClaw Memory System]]
