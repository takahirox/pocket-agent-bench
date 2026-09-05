Combine the arrays in input/*.json. For each entity, select the event with greatest numeric version, regardless of file or row order. Omit entities whose selected event has deleted=true. Write output/result.json mapping remaining entity IDs to the selected value. Preserve inputs.
Workspace: /app. Python 3 standard library and Git are available.
