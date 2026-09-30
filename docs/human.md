# Human by Default

Sending too fast is how accounts get flagged. parley's `HumanPacing`:

- types for ~90 ms/character (bounded), jittered;
- sleeps a variable "network" beat before each *sent*;
- keeps a rolling burst budget (18 messages / 60 s by default).

Every value is overridable per command and per API call, because you are the responsible party for your own account.