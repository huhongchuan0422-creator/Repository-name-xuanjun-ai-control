"""Strict, variable-time Ed25519 verification for public inputs (RFC 8032)."""
import hashlib
Q=2**255-19
L=2**252+27742317777372353535851937790883648493
D=(-121665*pow(121666,Q-2,Q))%Q
I=pow(2,(Q-1)//4,Q)
IDENTITY=(0,1,1,0)

def _recover_x(y,sign):
    xx=(y*y-1)*pow(D*y*y+1,Q-2,Q)%Q
    x=pow(xx,(Q+3)//8,Q)
    if (x*x-xx)%Q:x=x*I%Q
    if (x*x-xx)%Q:raise ValueError('POINT_NOT_ON_CURVE')
    if (x&1)!=sign:x=Q-x
    if x==0 and sign:raise ValueError('POINT_NONCANONICAL')
    return x

def _decode(data):
    if len(data)!=32:raise ValueError('POINT_LENGTH')
    value=int.from_bytes(data,'little');y=value&((1<<255)-1);sign=value>>255
    if y>=Q:raise ValueError('POINT_NONCANONICAL')
    x=_recover_x(y,sign);return (x,y,1,x*y%Q)

def _add(p,q):
    x1,y1,z1,t1=p;x2,y2,z2,t2=q
    a=(y1-x1)*(y2-x2)%Q;b=(y1+x1)*(y2+x2)%Q
    c=2*D*t1*t2%Q;d=2*z1*z2%Q;e=(b-a)%Q;f=(d-c)%Q;g=(d+c)%Q;h=(b+a)%Q
    return (e*f%Q,g*h%Q,f*g%Q,e*h%Q)

def _mul(p,n):
    result=IDENTITY
    while n:
        if n&1:result=_add(result,p)
        p=_add(p,p);n>>=1
    return result

def _equal(a,b):return (a[0]*b[2]-b[0]*a[2])%Q==0 and (a[1]*b[2]-b[1]*a[2])%Q==0

BASE=_decode(bytes.fromhex('5866666666666666666666666666666666666666666666666666666666666666'))

def verify(public_key,message,signature):
    if not isinstance(public_key,bytes) or not isinstance(message,bytes) or not isinstance(signature,bytes) or len(public_key)!=32 or len(signature)!=64:return False
    try:
        a=_decode(public_key);r=_decode(signature[:32]);s=int.from_bytes(signature[32:],'little')
        if s>=L or _equal(_mul(a,8),IDENTITY) or _equal(_mul(r,8),IDENTITY):return False
        # Require prime-order subgroup points, ruling out mixed torsion encodings.
        if not _equal(_mul(a,L),IDENTITY) or not _equal(_mul(r,L),IDENTITY):return False
        h=int.from_bytes(hashlib.sha512(signature[:32]+public_key+message).digest(),'little')%L
        return _equal(_mul(BASE,s),_add(r,_mul(a,h)))
    except (ValueError,OverflowError):return False
