#define NOMINMAX
#include <fbxsdk.h>
#include <windows.h>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <vector>
#include <string>
#include <stdexcept>
#include <functional>
std::string utf8(const wchar_t* s){int n=WideCharToMultiByte(CP_UTF8,0,s,-1,0,0,0,0);std::string r(n,0);WideCharToMultiByte(CP_UTF8,0,s,-1,r.data(),n,0,0);r.pop_back();return r;}
int wmain(int argc,wchar_t** argv){try{
 if(argc!=3)throw std::runtime_error("usage: fbx_skeleton input.fbx skeleton.txt");
 auto m=FbxManager::Create();m->SetIOSettings(FbxIOSettings::Create(m,IOSROOT));auto s=FbxScene::Create(m,"");auto im=FbxImporter::Create(m,"");
 if(!im->Initialize(utf8(argv[1]).c_str(),-1,m->GetIOSettings())||!im->Import(s))throw std::runtime_error(im->GetStatus().GetErrorString());im->Destroy();
 FbxAxisSystem::MayaYUp.ConvertScene(s);FbxSystemUnit::cm.ConvertScene(s);
 std::vector<FbxNode*> nodes;std::vector<int> parents;
 std::function<void(FbxNode*,int)> walk=[&](FbxNode* n,int p){if(n->GetSkeleton()){int i=(int)nodes.size();nodes.push_back(n);parents.push_back(p);p=i;}for(int j=0;j<n->GetChildCount();j++)walk(n->GetChild(j),p);};walk(s->GetRootNode(),-1);
 if(nodes.empty())throw std::runtime_error("No skeleton nodes in FBX");
 std::ofstream out{std::filesystem::path(argv[2])};out<<std::setprecision(17)<<nodes.size()<<"\n";
 for(size_t i=0;i<nodes.size();i++){auto g=nodes[i]->EvaluateGlobalTransform(FBXSDK_TIME_INFINITE);auto t=g.GetT();auto q=g.GetQ();auto scale=g.GetS();out<<std::quoted(nodes[i]->GetName())<<" "<<parents[i];for(int k=0;k<3;k++)out<<" "<<t[k];for(int k=0;k<4;k++)out<<" "<<q[k];for(int k=0;k<3;k++)out<<" "<<scale[k];out<<"\n";}
 if(!out)throw std::runtime_error("Cannot write skeleton");std::cout<<"EXTRACTED bones="<<nodes.size()<<" units=cm up=Y default_reference_pose\n";m->Destroy();return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
