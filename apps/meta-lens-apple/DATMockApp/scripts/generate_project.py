#!/usr/bin/env python3
"""Generate the small debug-only iOS harness; stdlib only, no global Xcode changes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".generated" / "ChibiDATMock.xcodeproj"
objects = {}


def add(key, isa, **fields):
    identifier = hashlib.sha256(key.encode()).hexdigest()[:24].upper()
    objects[identifier] = dict(isa=isa, **fields)
    return identifier


def config_list(name, settings):
    conf = add(name + "-debug", "XCBuildConfiguration", name="Debug", buildSettings=settings)
    return add(name + "-configs", "XCConfigurationList", buildConfigurations=[conf],
               defaultConfigurationIsVisible=0, defaultConfigurationName="Debug")


def phase(name, isa, files):
    return add(name, isa, buildActionMask=2147483647, files=files,
               runOnlyForDeploymentPostprocessing=0)


def source_files(folder, suffix):
    refs, builds = [], []
    for path in sorted((ROOT / folder).glob("*" + suffix)):
        ref = add(str(path.relative_to(ROOT)), "PBXFileReference", lastKnownFileType="sourcecode.swift",
                  path="../" + str(path.relative_to(ROOT)), sourceTree="SOURCE_ROOT")
        refs.append(ref)
        builds.append(add(str(path.relative_to(ROOT)) + "-build", "PBXBuildFile", fileRef=ref))
    return refs, builds


remote = add("meta-sdk", "XCRemoteSwiftPackageReference",
             repositoryURL="https://github.com/facebook/meta-wearables-dat-ios",
             requirement={"kind": "exactVersion", "version": "1.0.1"})
local = add("lens-core", "XCLocalSwiftPackageReference", relativePath="../..")
deps = [add("product-" + name, "XCSwiftPackageProductDependency", package=package, productName=name)
        for name, package in [("MWDATCore", remote), ("MWDATCamera", remote),
                              ("MWDATMockDevice", remote), ("ChibiLensCore", local)]]
links = [add("link-" + dep, "PBXBuildFile", productRef=dep) for dep in deps]
app_ref = add("app-product", "PBXFileReference", explicitFileType="wrapper.application",
              path="ChibiDATMock.app", sourceTree="BUILT_PRODUCTS_DIR")
test_ref = add("test-product", "PBXFileReference", explicitFileType="wrapper.cfbundle",
               path="ChibiDATMockTests.xctest", sourceTree="BUILT_PRODUCTS_DIR")
sources, builds = source_files("Sources", ".swift")
tests, test_builds = source_files("Tests", ".swift")
video = add("video", "PBXFileReference", lastKnownFileType="file", path="../Resources/charger-label.mp4",
            sourceTree="SOURCE_ROOT")
resource_build = add("video-build", "PBXBuildFile", fileRef=video)
products = add("products", "PBXGroup", children=[app_ref, test_ref], name="Products", sourceTree="<group>")
group = add("root-group", "PBXGroup", children=sources + tests + [video, products], sourceTree="<group>")
common = {"SDKROOT": "iphoneos", "IPHONEOS_DEPLOYMENT_TARGET": "17.2", "SWIFT_VERSION": "6.0",
          "SWIFT_STRICT_CONCURRENCY": "complete", "TARGETED_DEVICE_FAMILY": "1,2",
          "CODE_SIGNING_ALLOWED": "NO", "DEBUG_INFORMATION_FORMAT": "dwarf", "SWIFT_OPTIMIZATION_LEVEL": "-Onone",
          "SWIFT_ACTIVE_COMPILATION_CONDITIONS": "DEBUG", "ENABLE_TESTABILITY": "YES",
          "CLANG_ENABLE_MODULES": "YES", "SUPPORTED_PLATFORMS": "iphoneos iphonesimulator"}
app = add("app", "PBXNativeTarget", name="ChibiDATMock", productName="ChibiDATMock",
          productReference=app_ref, productType="com.apple.product-type.application",
          buildConfigurationList=config_list("app", dict(common,
              PRODUCT_BUNDLE_IDENTIFIER="cloud.taika.chibi.datmock", PRODUCT_NAME="$(TARGET_NAME)",
              INFOPLIST_FILE="../Info.plist", GENERATE_INFOPLIST_FILE="NO",
              LD_RUNPATH_SEARCH_PATHS=["$(inherited)", "@executable_path/Frameworks"])),
          buildPhases=[phase("app-sources", "PBXSourcesBuildPhase", builds),
                       phase("app-frameworks", "PBXFrameworksBuildPhase", links),
                       phase("app-resources", "PBXResourcesBuildPhase", [resource_build])],
          buildRules=[], dependencies=[], packageProductDependencies=deps)
proxy = add("app-proxy", "PBXContainerItemProxy", containerPortal="PROJECT_ID", proxyType=1,
            remoteGlobalIDString=app, remoteInfo="ChibiDATMock")
dependency = add("test-app-dependency", "PBXTargetDependency", target=app, targetProxy=proxy)
test = add("test", "PBXNativeTarget", name="ChibiDATMockTests", productName="ChibiDATMockTests",
           productReference=test_ref, productType="com.apple.product-type.bundle.unit-test",
           buildConfigurationList=config_list("test", dict(common,
               PRODUCT_BUNDLE_IDENTIFIER="cloud.taika.chibi.datmock.tests", PRODUCT_NAME="$(TARGET_NAME)",
               GENERATE_INFOPLIST_FILE="YES", BUNDLE_LOADER="$(TEST_HOST)",
               TEST_HOST="$(BUILT_PRODUCTS_DIR)/ChibiDATMock.app/ChibiDATMock",
               LD_RUNPATH_SEARCH_PATHS=["$(inherited)", "@executable_path/Frameworks", "@loader_path/Frameworks"])),
           buildPhases=[phase("test-sources", "PBXSourcesBuildPhase", test_builds),
                        phase("test-frameworks", "PBXFrameworksBuildPhase", [])],
           buildRules=[], dependencies=[dependency])
project = add("project", "PBXProject", attributes={"LastUpgradeCheck": "2640"}, compatibilityVersion="Xcode 14.0",
              buildConfigurationList=config_list("project", common), developmentRegion="en",
              knownRegions=["en", "Base"], mainGroup=group, productRefGroup=products,
              projectDirPath="", projectRoot="", packageReferences=[remote, local], targets=[app, test])
objects[proxy]["containerPortal"] = project


def encode(value, indent=0):
    if isinstance(value, dict):
        return "{\n" + "\n".join("\t" * (indent + 1) + json.dumps(k) + " = " + encode(v, indent + 1) + ";"
                                  for k, v in value.items()) + "\n" + "\t" * indent + "}"
    if isinstance(value, list):
        return "(" + ", ".join(encode(v, indent) for v in value) + ")"
    return str(value) if isinstance(value, int) else json.dumps(value)


OUTPUT.mkdir(parents=True, exist_ok=True)
(OUTPUT / "project.pbxproj").write_text("// !$*UTF8*$!\n" + encode({
    "archiveVersion": 1, "classes": {}, "objectVersion": 56, "objects": objects, "rootObject": project}) + "\n")
scheme = OUTPUT / "xcshareddata" / "xcschemes" / "ChibiDATMock.xcscheme"
scheme.parent.mkdir(parents=True, exist_ok=True)
scheme.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2640" version="1.3">
  <BuildAction parallelizeBuildables="NO" buildImplicitDependencies="YES"><BuildActionEntries>
    <BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="NO" buildForArchiving="NO" buildForAnalyzing="YES">
      <BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{app}" BuildableName="ChibiDATMock.app" BlueprintName="ChibiDATMock" ReferencedContainer="container:ChibiDATMock.xcodeproj"/>
    </BuildActionEntry>
  </BuildActionEntries></BuildAction>
  <TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES">
    <Testables><TestableReference skipped="NO"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{test}" BuildableName="ChibiDATMockTests.xctest" BlueprintName="ChibiDATMockTests" ReferencedContainer="container:ChibiDATMock.xcodeproj"/></TestableReference></Testables>
  </TestAction>
  <LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{app}" BuildableName="ChibiDATMock.app" BlueprintName="ChibiDATMock" ReferencedContainer="container:ChibiDATMock.xcodeproj"/></BuildableProductRunnable></LaunchAction>
</Scheme>
''')
print(OUTPUT)
