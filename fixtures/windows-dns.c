#include <winsock2.h>
#include <windows.h>
#include <iphlpapi.h>
#include <stdio.h>
#include <stdlib.h>
int main(void) {
 ULONG size=sizeof(FIXED_INFO);FIXED_INFO *info=malloc(size);
 if(GetNetworkParams(info,&size)==ERROR_BUFFER_OVERFLOW){free(info);info=malloc(size);}
 DWORD r=GetNetworkParams(info,&size);printf("GetNetworkParams: %lu\n",(unsigned long)r);
 if(r==NO_ERROR){IP_ADDR_STRING *s=&info->DnsServerList;for(;s;s=s->Next){printf("DNS: %s\n",s->IpAddress.String);}}
 free(info);
 WSADATA ws;WSAStartup(MAKEWORD(2,2),&ws);
 const char *servers[]={"192.168.5.1","119.29.29.29","1.1.1.1"};
 for(int i=0;i<3;i++){
  SOCKET sock=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);DWORD timeout=3000;
  setsockopt(sock,SOL_SOCKET,SO_RCVTIMEO,(const char*)&timeout,sizeof(timeout));
  struct sockaddr_in dest={0};dest.sin_family=AF_INET;dest.sin_port=htons(53);dest.sin_addr.s_addr=inet_addr(servers[i]);
  unsigned char query[]={0x12,0x34,1,0,0,1,0,0,0,0,0,0,7,'e','x','a','m','p','l','e',3,'c','o','m',0,0,1,0,1};
  int n=sendto(sock,(const char*)query,sizeof(query),0,(struct sockaddr*)&dest,sizeof(dest));printf("UDP DNS %s sent=%d error=%d\n",servers[i],n,WSAGetLastError());
  char response[2048];n=recv(sock,response,sizeof(response),0);printf("UDP DNS %s received=%d error=%d\n",servers[i],n,WSAGetLastError());
  closesocket(sock);
 }
 WSACleanup();return r?1:0;
}
