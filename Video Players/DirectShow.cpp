#include "dshow.h"
#pragma comment(lib, "Strmiids.lib")

int main() {
  IGraphBuilder* pGraph = NULL;
  IMediaControl* pControl = NULL;
  IMediaEvent* pEvent = NULL;

  CoInitialize(NULL);
  CoCreateInstance(CLSID_FilterGraph, NULL, CLSCTX_INPROC_SERVER,
                   IID_IGraphBuilder, (void**)&pGraph);

  pGraph->QueryInterface(IID_IMediaControl, (void**)&pControl);
  pGraph->QueryInterface(IID_IMediaEvent, (void**)&pEvent);
  pGraph->RenderFile(L"D:\\.avi", NULL);

  pControl->Run();

  long evCode = 0;
  pEvent->WaitForCompletion(INFINITE, &evCode);

  pControl->Release();
  pEvent->Release();
  pGraph->Release();

  CoUninitialize();
  return 0;
}
