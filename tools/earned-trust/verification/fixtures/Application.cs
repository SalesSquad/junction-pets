// Frozen reproduction of MessagePack-CSharp issue #2283.
using MessagePack;
using Lib;

namespace App;

[MessagePackObject]
public sealed partial record Cmd([property: Key(0)] string Scope)
{
    [Key(1)]
    public Item<int> Member { get; init; }
}

[GeneratedMessagePackResolver]
partial class AppResolver { }
