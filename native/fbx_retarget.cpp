// Standalone FBX SDK helper. No Unreal headers or modules.
#define NOMINMAX
#include <fbxsdk.h>
#include <fstream>
#include <iostream>
#include <vector>
#include <string>
#include <cmath>
#include <algorithm>
#include <stdexcept>
#include <filesystem>
#include <windows.h>

std::string utf8(const wchar_t* value) {
    int n=WideCharToMultiByte(CP_UTF8,0,value,-1,nullptr,0,nullptr,nullptr);
    std::string result(n,'\0');
    WideCharToMultiByte(CP_UTF8,0,value,-1,result.data(),n,nullptr,nullptr);
    result.resize(n-1);
    return result;
}

int wmain(int argc, wchar_t** argv) {
    try {
        if (argc != 3) throw std::runtime_error("usage: fbx_export input.txt output.fbx");
        std::ifstream in{std::filesystem::path(argv[1])};
        const auto outputPath=utf8(argv[2]);
        int bones, frames; double fps;
        if (!(in >> bones >> frames >> fps) || bones < 1 || bones > 1024 || frames < 1 || frames > 100000 || !(fps > 0 && fps < 1000)) throw std::runtime_error("bad header");
        auto manager = FbxManager::Create();
        manager->SetIOSettings(FbxIOSettings::Create(manager, IOSROOT));
        auto scene = FbxScene::Create(manager,"Movie2AnimStandalone");
        scene->GetGlobalSettings().SetAxisSystem(FbxAxisSystem::MayaYUp);
        scene->GetGlobalSettings().SetSystemUnit(FbxSystemUnit::cm);
        scene->GetGlobalSettings().SetTimeMode(FbxTime::eCustom);
        scene->GetGlobalSettings().SetCustomFrameRate(fps);
        std::vector<FbxNode*> nodes;
        for (int i=0;i<bones;i++) {
            std::string name; int parent; double x,y,z,rx,ry,rz;
            if (!(in >> name >> parent >> x >> y >> z >> rx >> ry >> rz) || parent >= i || parent < -1 || (i>0 && parent<0)) throw std::runtime_error("bad skeleton");
            auto node = FbxNode::Create(scene,name.c_str());
            auto bone = FbxSkeleton::Create(scene,(name+"_bone").c_str());
            bone->SetSkeletonType(i==0?FbxSkeleton::eRoot:FbxSkeleton::eLimbNode);
            bone->Size.Set(2.0);
            node->SetNodeAttribute(bone);
            node->SetRotationOrder(FbxNode::eSourcePivot,eEulerXYZ);
            node->LclTranslation.Set(FbxDouble3(x,y,z));
            node->LclRotation.Set(FbxDouble3(rx,ry,rz));
            (parent<0?scene->GetRootNode():nodes[parent])->AddChild(node);
            nodes.push_back(node);
        }
        auto stack = FbxAnimStack::Create(scene,"Motion");
        auto layer = FbxAnimLayer::Create(scene,"BaseLayer");
        stack->AddMember(layer);
        FbxTime stop; stop.SetSecondDouble((frames-1)/fps);
        FbxTime begin; begin.SetSecondDouble(0);
        stack->SetLocalTimeSpan(FbxTimeSpan(begin,stop));
        scene->GetGlobalSettings().SetTimelineDefaultTimeSpan(FbxTimeSpan(begin,stop));
        std::vector<double> original;
        const char* channels[]={FBXSDK_CURVENODE_COMPONENT_X,FBXSDK_CURVENODE_COMPONENT_Y,FBXSDK_CURVENODE_COMPONENT_Z};
        for(int f=0;f<frames;f++) {
            FbxTime time; time.SetSecondDouble(f/fps);
            for(int k=0;k<bones*6;k++) {
                double value;
                if(!(in>>value) || !std::isfinite(value)) throw std::runtime_error("bad animation key");
                original.push_back(value);
                FbxAnimCurve* curve = k%6<3 ? nodes[k/6]->LclTranslation.GetCurve(layer,channels[k%6],true) : nodes[k/6]->LclRotation.GetCurve(layer,channels[k%6-3],true);
                curve->KeyModifyBegin();
                int key = curve->KeyAdd(time);
                curve->KeySetValue(key,(float)value);
                curve->KeySetInterpolation(key,FbxAnimCurveDef::eInterpolationLinear);
                curve->KeyModifyEnd();
            }
        }
        auto pose=FbxPose::Create(scene,"ReferencePose");
        pose->SetIsBindPose(true);
        for(auto node:nodes) { auto mat=node->EvaluateGlobalTransform(FBXSDK_TIME_INFINITE); pose->Add(node,mat); }
        scene->AddPose(pose);
        auto exporter=FbxExporter::Create(manager,"");
        if(!exporter->Initialize(outputPath.c_str(),-1,manager->GetIOSettings()) || !exporter->Export(scene)) throw std::runtime_error(exporter->GetStatus().GetErrorString());
        exporter->Destroy();
        auto imported=FbxScene::Create(manager,"RoundTrip");
        auto importer=FbxImporter::Create(manager,"");
        if(!importer->Initialize(outputPath.c_str(),-1,manager->GetIOSettings()) || !importer->Import(imported)) throw std::runtime_error("FBX re-import failed");
        importer->Destroy();
        double maxError=0;
        for(int f=0;f<frames;f++) {
            FbxTime time; time.SetSecondDouble(f/fps);
            for(int i=0;i<bones;i++) {
                auto node=imported->FindNodeByName(nodes[i]->GetName());
                if(!node) throw std::runtime_error("missing re-imported bone");
                auto expected=nodes[i]->EvaluateLocalTransform(time);
                auto actual=node->EvaluateLocalTransform(time);
                if(node->GetParent()->GetName()!=std::string(nodes[i]->GetParent()->GetName())) throw std::runtime_error("parent mismatch");
                for(int r=0;r<4;r++)for(int c=0;c<4;c++)maxError=std::max(maxError,std::abs(expected.Get(r,c)-actual.Get(r,c)));
            }
        }
        if(maxError>1e-4) throw std::runtime_error("FBX roundtrip transform mismatch");
        std::cout<<"FBX_ROUNDTRIP_OK bones="<<bones<<" frames="<<frames<<" fps="<<fps<<" max_matrix_error="<<maxError<<"\n";
        manager->Destroy();
        return 0;
    } catch(const std::exception& e) { std::cerr<<e.what()<<"\n"; return 1; }
}
