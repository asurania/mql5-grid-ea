# Journal Dashboard

## Recent journal notes

```dataview
TABLE file.name AS Note, file.mtime AS Updated
FROM "second-brain/journal"
SORT file.name DESC
LIMIT 14
```

## Related

- [[HOME]]
- [[Second Brain]]
- [[MEMORY]]
