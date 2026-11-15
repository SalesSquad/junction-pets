// Frozen reproduction of MessagePack-CSharp issue #2283.
using MessagePack;

namespace Lib;

[MessagePackObject]
public partial record struct Item<T>([property: Key(0)] string Key);
