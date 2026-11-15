using System.Collections.Immutable;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using MessagePack;
using MessagePack.SourceGenerator;
using MessagePack.SourceGenerator.Analyzers;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Diagnostics;

// This executable and the two input files are copied byte-for-byte to both
// isolated builds. A build failure never becomes a behavioral test failure.
const string caseId = "MP2283-metadata-generic-struct-resolver";
const string expectedResolver = "App.AppResolver.g.cs";
string fixtureRoot = Path.Combine(AppContext.BaseDirectory, "fixtures");
string resultPath = args.Single();
string libraryText = File.ReadAllText(Path.Combine(fixtureRoot, "Library.cs"));
string applicationText = File.ReadAllText(Path.Combine(fixtureRoot, "Application.cs"));
var parseOptions = CSharpParseOptions.Default.WithLanguageVersion(LanguageVersion.CSharp12);

string[] platformAssemblies = ((string?)AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES")
    ?? throw new InvalidOperationException("Runtime assembly inventory is unavailable."))
    .Split(Path.PathSeparator);
string[] assemblyPaths = platformAssemblies
    .Append(typeof(MessagePackObjectAttribute).Assembly.Location)
    .Append(typeof(MessagePackSerializer).Assembly.Location)
    .Distinct(StringComparer.Ordinal).OrderBy(p => p, StringComparer.Ordinal).ToArray();
MetadataReference[] references = assemblyPaths.Select(p => MetadataReference.CreateFromFile(p)).ToArray();

CSharpCompilation Compile(string name, string text, IEnumerable<MetadataReference> refs) =>
    CSharpCompilation.Create(name,
        [CSharpSyntaxTree.ParseText(text, parseOptions, name + ".cs")],
        refs, new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));

static object Describe(Diagnostic diagnostic) => new
{
    id = diagnostic.Id,
    severity = diagnostic.Severity.ToString().ToLowerInvariant(),
    message = diagnostic.GetMessage(),
    location = diagnostic.Location.ToString(),
};

var libraryCompilation = Compile("FrozenExternalLibrary", libraryText, references);
using var libraryImage = new MemoryStream();
var libraryEmit = libraryCompilation.Emit(libraryImage);
if (!libraryEmit.Success)
{
    var invalid = new
    {
        caseId,
        status = "inconclusive",
        reason = "Frozen library input did not compile; no behavioral claim is possible.",
        diagnostics = libraryEmit.Diagnostics.Select(Describe).ToArray(),
        generatedResolver = new { expectedHintName = expectedResolver, present = (bool?)null },
        tests = new { passed = 0, failed = 0, skipped = 0 },
    };
    File.WriteAllText(resultPath, JsonSerializer.Serialize(invalid, new JsonSerializerOptions { WriteIndented = true }) + "\n");
    return 2;
}

var appCompilation = Compile("FrozenApplication", applicationText,
    references.Append(MetadataReference.CreateFromImage(libraryImage.ToArray())));
ImmutableArray<Diagnostic> analyzerDiagnostics = await appCompilation
    .WithAnalyzers(ImmutableArray.Create<DiagnosticAnalyzer>(new MsgPack00xMessagePackAnalyzer()))
    .GetAnalyzerDiagnosticsAsync();

GeneratorDriver driver = CSharpGeneratorDriver.Create(
    generators: [new MessagePackGenerator().AsSourceGenerator()], parseOptions: parseOptions);
driver = driver.RunGeneratorsAndUpdateCompilation(appCompilation, out var generatedCompilation, out var driverDiagnostics);
GeneratorDriverRunResult generated = driver.GetRunResult();
Diagnostic[] compilerErrors = generatedCompilation.GetDiagnostics()
    .Where(d => d.Severity == DiagnosticSeverity.Error).ToArray();
var outputs = generated.Results.SelectMany(r => r.GeneratedSources).Select(source => new
{
    hintName = source.HintName,
    sha256 = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(source.SourceText.ToString()))).ToLowerInvariant(),
    text = source.SourceText.ToString(),
}).OrderBy(x => x.hintName, StringComparer.Ordinal).ToArray();
bool resolverPresent = outputs.Any(x => x.hintName == expectedResolver);
bool analyzerCrash = analyzerDiagnostics.Any(d => d.Id == "AD0001");
bool generatorCrash = generated.Results.Any(r => r.Exception is not null)
    || driverDiagnostics.Any(d => d.Id == "CS8785");
bool blockingDiagnostics = analyzerDiagnostics.Concat(driverDiagnostics)
    .Any(d => d.Severity >= DiagnosticSeverity.Warning);
bool passed = !analyzerCrash && !generatorCrash && !blockingDiagnostics
    && compilerErrors.Length == 0 && resolverPresent;

var result = new
{
    caseId,
    status = passed ? "pass" : "fail",
    checks = new
    {
        libraryCompiled = true,
        analyzerDidNotCrash = !analyzerCrash,
        generatorDidNotCrash = !generatorCrash,
        noBlockingDiagnostics = !blockingDiagnostics,
        generatedCodeCompiles = compilerErrors.Length == 0,
        consumerResolverGenerated = resolverPresent,
    },
    diagnostics = analyzerDiagnostics.Concat(driverDiagnostics).Concat(compilerErrors).Select(Describe).ToArray(),
    exceptions = generated.Results.Where(r => r.Exception is not null).Select(r => r.Exception!.ToString()).ToArray(),
    generatedResolver = new { expectedHintName = expectedResolver, present = resolverPresent },
    generatedSources = outputs,
    runtimeAssemblies = assemblyPaths.Select(path => new
    {
        name = Path.GetFileName(path),
        sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant(),
    }).ToArray(),
    tests = new { passed = passed ? 1 : 0, failed = passed ? 0 : 1, skipped = 0 },
};
File.WriteAllText(resultPath, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }) + "\n");
Console.WriteLine($"{caseId}: {(passed ? "PASS" : "FAIL")}; analyzerCrash={analyzerCrash}; generatorCrash={generatorCrash}; resolverPresent={resolverPresent}; compilerErrors={compilerErrors.Length}");
return passed ? 0 : 1;
