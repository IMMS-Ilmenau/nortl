# Coverage Files

Coverage files are produced during simulation. They contain coverage information about noRTL engines, that can be back-annotated.

The files use the [JSON Lines](https://jsonlines.org/) format. They contain a list of JSON **records**, separated by **linebreaks**.
The individual records can be distinguished by their `type` property.

The individual records must not contain any linebreaks (`\n` characters). Other whitespace is ignored.
This allows parsers to split the file content into a list of records.

They properties of the individual coverage records are described below.

## Info Record

The information records contains information about the associated engine and optionally the test case.

It contains a SHA256 checksum of the engine information.
The checksum is used to check if the coverage data matches the engine or if it is wrongly associated or outdated.

Only **one** info record must be present in each coverage file.

```typescript
interface InfoRecord {
    type: "info"
    engine: EngineReference
    test: TestInfo | null
}

interface EngineReference {
    name: string
    sha256sum: string
}

interface TestInfo {
    name: string
    start_time: string
}
```

## State Coverage

This record indicates coverage for a state, i.e. if this state was visited.
The state is referenced by its name.

```typescript
interface StateCoverageRecord {
    type: "state"
    state: string
    covered: boolean
}
```

## Transition Coverage

This record indicates coverage for a transition between two states, i.e. if this transition was taken.

```typescript
interface TransitionCoverageRecord {
    type: "transition"
    source: string
    target: string
    covered: boolean
}
```

## Cover Point

Cover points can occur multiple times in each coverage file.

It is recommended to emit each cover point with `covered=false` to define it.

The combination of `state`, `condition` and `point_name` is used as a key, i.e. each unique combination will result in a different cover point.
`group_name` and `group_coords` must be identical for all records of one cover point.

```typescript
interface CoverPointRecord {
    type: "coverpoint"
    state: string
    condition: string
    point_name: string
    group_name: string | null
    group_coords: Array<number> | null
    covered: boolean
}
```

## Cover Group

Only **one** record must be present **per cover group** in each coverage file.

```typescript
interface CoverGroupRecord {
    type: "covergroup"
    name: string
    axis: Array<string>
    limits: Array<Array<number>> // (1)!
}
```

1. Each element in the `limits` array must have 2 elements, the lower and upper limits.
