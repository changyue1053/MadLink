"""Minimal native Xcode projects. No third-party generator or handcrafted framework plist."""
import json
from pathlib import Path

def generate(folder, producer=False):
    folder=Path(folder);objects={};counter=0
    def obj(isa,**kw):
        nonlocal counter
        counter+=1;k=f'{counter:024X}';objects[k]={'isa':isa,**kw};return k
    def ref(path,typ,tree='<group>'): return obj('PBXFileReference',path=path,lastKnownFileType=typ,sourceTree=tree)
    def phase(kind,files):return obj(kind,buildActionMask=2147483647,files=files,runOnlyForDeploymentPostprocessing=0)
    def build(r,public=False):return obj('PBXBuildFile',fileRef=r,**({'settings':{'ATTRIBUTES':['Public']}} if public else {}))
    products=[];children=[];targets=[]
    def target(name,kind,sources,libs,extra,headers=()):
        refs=[ref(p,'sourcecode.cpp.objcpp' if p.endswith('.mm') else 'sourcecode.cpp.cpp') for p in sources];children.extend(refs)
        librefs=[ref(p,t) for p,t in libs];children.extend(librefs)
        phases=[phase('PBXSourcesBuildPhase',[build(r) for r in refs]),phase('PBXFrameworksBuildPhase',[build(r) for r in librefs])]
        if headers:
            hr=[ref(p,'sourcecode.c.h') for p in headers];children.extend(hr);phases.append(phase('PBXHeadersBuildPhase',[build(r,True) for r in hr]))
        ext={'framework':'.framework','application':'.app','bundle.unit-test':'.xctest'}[kind]
        product=ref(name+ext,{'framework':'wrapper.framework','application':'wrapper.application','bundle.unit-test':'wrapper.cfbundle'}[kind],'BUILT_PRODUCTS_DIR');products.append(product)
        settings={'PRODUCT_NAME':name,'PRODUCT_BUNDLE_IDENTIFIER':'org.madlink.preview.'+name,'GENERATE_INFOPLIST_FILE':'YES','IPHONEOS_DEPLOYMENT_TARGET':'15.0','SDKROOT':'iphoneos','SUPPORTED_PLATFORMS':'iphoneos iphonesimulator','ARCHS':'arm64','ONLY_ACTIVE_ARCH':'NO','CLANG_CXX_LANGUAGE_STANDARD':'c++17','CLANG_CXX_LIBRARY':'libc++','GCC_ENABLE_CPP_EXCEPTIONS':'YES','CLANG_ENABLE_OBJC_ARC':'YES','CLANG_ENABLE_MODULES':'YES','CLANG_MODULES_AUTOLINK':'YES','CODE_SIGNING_ALLOWED':'NO',**extra}
        configs=[obj('XCBuildConfiguration',name=n,buildSettings=settings) for n in ('Debug','Release')]
        cl=obj('XCConfigurationList',buildConfigurations=configs,defaultConfigurationIsVisible=0,defaultConfigurationName='Release')
        t=obj('PBXNativeTarget',name=name,productName=name,productType='com.apple.product-type.'+kind,productReference=product,buildConfigurationList=cl,buildPhases=phases,buildRules=[],dependencies=[]);targets.append(t);return t
    if producer:
        main=target('MadLink','framework',['madlink.cpp','madlink_c.cpp'],[],{'MACH_O_TYPE':'staticlib','DEFINES_MODULE':'YES','MODULEMAP_FILE':'$(SRCROOT)/module.modulemap','SKIP_INSTALL':'NO','BUILD_LIBRARY_FOR_DISTRIBUTION':'YES','PUBLIC_HEADERS_FOLDER_PATH':'$(CONTENTS_FOLDER_PATH)/Headers'},['madlink_c.h'])
        tests=None
    else:
        main=target('Demo','application',['App.mm','Smoke.mm'],[('MadLink.xcframework','wrapper.xcframework')],{'OTHER_LDFLAGS':['-lc++','-framework','Foundation','-framework','UIKit'],'TARGETED_DEVICE_FAMILY':'1,2','INFOPLIST_KEY_UILaunchScreen_Generation':'YES'})
        tests=target('SmokeTests','bundle.unit-test',['Tests.mm'],[],{'TEST_HOST':'$(BUILT_PRODUCTS_DIR)/Demo.app/Demo','BUNDLE_LOADER':'$(TEST_HOST)',
            'OTHER_LDFLAGS':['-lc++','-framework','Foundation','-framework','XCTest'],
            'FRAMEWORK_SEARCH_PATHS':['$(inherited)','$(PLATFORM_DIR)/Developer/Library/Frameworks']})
        proxy=obj('PBXContainerItemProxy',containerPortal='000000000000000000000000',proxyType=1,remoteGlobalIDString=main,remoteInfo='Demo')
        dep=obj('PBXTargetDependency',target=main,targetProxy=proxy);objects[tests]['dependencies']=[dep]
    pg=obj('PBXGroup',children=products,name='Products',sourceTree='<group>');group=obj('PBXGroup',children=children+[pg],sourceTree='<group>')
    cfg=[obj('XCBuildConfiguration',name=n,buildSettings={}) for n in ('Debug','Release')]
    cl=obj('XCConfigurationList',buildConfigurations=cfg,defaultConfigurationIsVisible=0,defaultConfigurationName='Release')
    project=obj('PBXProject',buildConfigurationList=cl,compatibilityVersion='Xcode 14.0',developmentRegion='en',hasScannedForEncodings=0,knownRegions=['en'],mainGroup=group,productRefGroup=pg,projectDirPath='',projectRoot='',targets=targets,attributes={'LastUpgradeCheck':'2620'})
    if not producer:objects[proxy]['containerPortal']=project
    def encode(v):
        if isinstance(v,dict):return '{ '+''.join(json.dumps(k)+' = '+encode(x)+'; ' for k,x in v.items())+'}'
        if isinstance(v,list):return '('+','.join(encode(x) for x in v)+')'
        return json.dumps(str(v))
    projectdir=folder/'Preview.xcodeproj';projectdir.mkdir()
    (projectdir/'project.pbxproj').write_text('// !$*UTF8*$!\n'+encode({'archiveVersion':1,'classes':{},'objectVersion':56,'objects':objects,'rootObject':project}))
    schemes=projectdir/'xcshareddata/xcschemes';schemes.mkdir(parents=True)
    def entry(t):return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{t}" BuildableName="{objects[t]["productName"]}{".framework" if producer else (".app" if t==main else ".xctest")}" BlueprintName="{objects[t]["name"]}" ReferencedContainer="container:Preview.xcodeproj"/>'
    (schemes/'Preview.xcscheme').write_text('<Scheme version="1.3"><BuildAction><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">'+entry(main)+'</BuildActionEntry></BuildActionEntries></BuildAction><TestAction buildConfiguration="Debug" shouldUseLaunchSchemeArgsEnv="YES"><Testables>'+('' if not tests else '<TestableReference skipped="NO">'+entry(tests)+'</TestableReference>')+'</Testables></TestAction><LaunchAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="NO"/></Scheme>')
