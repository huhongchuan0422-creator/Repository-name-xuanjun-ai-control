"""Fixed 211a9 product admission for the ORIGINAL preview workflow, never deployment.
GITHUB_SHA remains the control revision. No arbitrary artifact/ref/product is accepted.
"""
import argparse, datetime, hashlib, io, json, os, re, stat, tempfile, time, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
BRANCH = 'feature/chatgpt-community-wechat-sp-offline-20261017'
WORKFLOW = '.github/workflows/chatgpt-community-wechat-sp-offline.yml'
PRODUCT_SHA = '211a9f4a1425c4b2667c13052b8590c0af3b3ac1'
PRODUCT_RUN = 40871297771
PRODUCT_JOB = 123438740248
ARTIFACT_ID = 12897330655
ARTIFACT_SIZE = 12684828
ARTIFACT_SHA256 = '0ae29468bdecce636e063cfdbe259c41db2fb72c79f0eb2f4fc7cf3bdb85d033'
SOURCE_SHA256 = '0b326fc77a109c2b061eba3146dcee47acb07c49f5e0aa08e92bf4ee4cdc18f9'
MANIFEST_SHA256 = 'f71eb501b8c73824ae8d2dd552e2feecbfb8b322710b95b65b8b62bd722a42a6'
APPID = 'wx1d5f8873eaea5392'
PROFILE = 'uk-path-candidate'
BASE_URL = 'https://uk.wenwenwenyiyiyi.work/community-preview'
CONNECTED_APP_SHA256 = '07eaedb76bc73f278eeab7235cf2f921cee0c875f890fdc26c82fb4e4699b42e'
MAX_BYTES = 20000000
# Exact actual product evidence archive; no arbitrary extra member admission.
ARTIFACT_MEMBERS = {
  "community-stage-source.zip": [
    5933336,
    "0b326fc77a109c2b061eba3146dcee47acb07c49f5e0aa08e92bf4ee4cdc18f9"
  ],
  "community-admin-browser-evidence/16-community-home-1440.png": [
    222829,
    "9ef7897f0c7f8eae7a3c10a2c169a3ec8cc12d0b234271b5424e48352f32195d"
  ],
  "community-tests.log": [
    603588,
    "fc48904bc1b5ab0edc8e222840779a2ffb1cbcc7bb1ff445aee31f1048f1a8e4"
  ],
  "stage5-tests.log": [
    45344,
    "5c65a57acf6615aaf5e992b52ed022ebbd515f7ef0e287bfc6cacb524108b138"
  ],
  "community-admin-browser-evidence/16-community-home-390.png": [
    160800,
    "3f55528a7a910a66e16b813ea0fd5474f809070944b32b37dc6ec8f6d7c8764b"
  ],
  "community-admin-browser-evidence/16-logout-neutral-1440.png": [
    124506,
    "929647539550270dd2e33979c8d42d11353e426c1c31e4649c6ee0a4e2d2cfc2"
  ],
  "community-admin-browser-evidence/18-denied-cleared-1440.png": [
    83125,
    "bac3a0b6a8f5055016f5f936d273b7808c45a31b329690bcad4facd82e055523"
  ],
  "community-admin-browser-evidence/18-detail-1440.png": [
    104987,
    "4484b9fee0ea7ad8362c8ea26845e7843d5595f5064c5aff3862024b25a592c9"
  ],
  "community-admin-browser-evidence/18-edit-1440.png": [
    103560,
    "b8b0d6b7654caae34104ca32f50d7c69074e103c3c27d91d35ff47e9ba3d0342"
  ],
  "community-admin-browser-evidence/18-list-1440.png": [
    123882,
    "66d4d1570a2fb5793587fd3aef3d4cad8901480c7d3edb359ff6e991e4bc11f2"
  ],
  "community-admin-browser-evidence/18-readback-1440.png": [
    108698,
    "66876face62414945713f59d95f72fd2b86a16e203c563af322e357e2f73909e"
  ],
  "community-admin-browser-evidence/18-register-before-submit-1440.png": [
    108399,
    "34dac62a55f68e018e5985d3df973302e5125bb712b7a636f726185d8d666af6"
  ],
  "community-admin-browser-evidence/18-return-1440.png": [
    127158,
    "0287500a621395333ed78eb0d38aa6d7f5a9fe694ff9b3db43b325068f350a20"
  ],
  "community-admin-browser-evidence/19-denied-cleared-1440.png": [
    81572,
    "4dd66d797a43fd77df3b5fda68267de2ae9344c5a933be5350280daad96e8d5c"
  ],
  "community-admin-browser-evidence/19-detail-1440.png": [
    129775,
    "c3f6913c1ebe45747134a74039bfd4a7607513f910670f0e62eb3a431eead75c"
  ],
  "community-admin-browser-evidence/19-list-1440.png": [
    110203,
    "2f706c190ae46b12f30d1383b6cd7677a682e65675b9d0b3046c2dac1e91d48b"
  ],
  "community-admin-browser-evidence/19-return-1440.png": [
    110203,
    "2f706c190ae46b12f30d1383b6cd7677a682e65675b9d0b3046c2dac1e91d48b"
  ],
  "community-admin-browser-evidence/20-before-query-1440.png": [
    143291,
    "e2144af296a7df501415d47f0e4e028abc565c34fe026738d8736cb2c985c300"
  ],
  "community-admin-browser-evidence/20-denied-cleared-1440.png": [
    142237,
    "ec3f46e5a00449b0a0a227447b02f947227f02040ce387762eb8d8bc78c593fc"
  ],
  "community-admin-browser-evidence/20-detail-empty-1440.png": [
    96071,
    "1e21c3a9147c55c003e63ce2fa33608589f5659d65af1d94ad7575bcdbdd1bc8"
  ],
  "community-admin-browser-evidence/20-list-empty-1440.png": [
    129656,
    "0c28daa05547729800fbf2b4e35dea9b81f3779f06b4f13f1a16f96406a10cc9"
  ],
  "community-admin-browser-evidence/20-nonempty-synthetic-1440.png": [
    132773,
    "93bdd61a4fd53a6309dee24cbe5c7f38ae5300a489294d5e8053b111de263470"
  ],
  "community-admin-browser-evidence/20-return-1440.png": [
    129647,
    "2ddcafaf8fa3647a4fe3bf7e845667d64ac145bbe7999d05a3d7ee2fef6e395c"
  ],
  "community-admin-browser-evidence/21-denied-cleared-1440.png": [
    94962,
    "2780f5fbbc8fe93343917f6ef162bfd149ad64ffc50754b955da1cc80f96b147"
  ],
  "community-admin-browser-evidence/21-list-1440.png": [
    120388,
    "9f6f9f1881650ea9e7cc32cf0a4bd05e2112894d3cd06d5f74c1111fd5c59107"
  ],
  "community-admin-browser-evidence/21-detail-1440.png": [
    121226,
    "a05f263a724a38066cd483cc3de938ddce77e8cc56a7ff8c1742ab9798882f04"
  ],
  "community-admin-browser-evidence/21-return-1440.png": [
    120371,
    "c5a0ada4b6830b0ab3cd5fda860c6b1c92cd4a76590aa74e4559074c34a6d61e"
  ],
  "community-admin-browser-evidence/21-state-readback-1440.png": [
    121529,
    "67d364d3bbbf792cc848d18d743251eeacf7f25b3277a8a4dcc2d4d722400840"
  ],
  "community-admin-browser-evidence/22-denied-cleared-1440.png": [
    98553,
    "d38edfa2b9e1c3c8ca5038cfd457b2dba4b060e0d380ee9ba2f501661021ae19"
  ],
  "community-admin-browser-evidence/22-list-1440.png": [
    122929,
    "d51548d6827be170cf926de6b71f4d1ae8e2d04643997a853e90af63e364365d"
  ],
  "community-admin-browser-evidence/22-readback-1440.png": [
    122923,
    "8618cbc134186ae246aab476166f4c0a5f580c6178f0be17d659e6da61aff7fa"
  ],
  "community-admin-browser-evidence/22-return-1440.png": [
    122923,
    "8618cbc134186ae246aab476166f4c0a5f580c6178f0be17d659e6da61aff7fa"
  ],
  "community-admin-browser-evidence/23-denied-cleared-1440.png": [
    104849,
    "c48bba273a5b7ed0afe522734c3a4e6071a9ae92f6ced5d22c7ca844d1fb1799"
  ],
  "community-admin-browser-evidence/23-list-synthetic-1440.png": [
    114867,
    "d851c68eb341756c8168103ce049389d970dd2a5dcc35246f5b787d2a83da089"
  ],
  "community-admin-browser-evidence/23-return-synthetic-1440.png": [
    114842,
    "2c1e6f109e0f60ad1cd64e438f897d63b336a89cac2b658337e58c5a9d99db2a"
  ],
  "community-admin-browser-evidence/24-refund-denied-cleared-1440.png": [
    105051,
    "6ad170e10b1dedada1270a7459771da23b5af33a1c79ab1d6eb6feae2d971ef0"
  ],
  "community-admin-browser-evidence/24-refund-list-synthetic-1440.png": [
    146697,
    "d33599de9733e7548ac67836ab6a986411fe6b3e40b577362a8ee527df298562"
  ],
  "community-admin-browser-evidence/24-refund-return-1440.png": [
    146695,
    "beaf60742c0de81883fe0c08f8eccfd1fd36276a7c8eae5841debe40dc68072a"
  ],
  "community-admin-browser-evidence/25-logout-neutral-1440.png": [
    124508,
    "b5ad8f26e7c9555af925361f924815d007dff90cc35ba06a5d149f0f3cb5540a"
  ],
  "community-admin-browser-evidence/25-platform-home-1440.png": [
    293984,
    "195a9177ed4468c217957177be02b2951ecfbe61f49efc77dc9f4270ee41e580"
  ],
  "community-admin-browser-evidence/25-platform-home-390.png": [
    219761,
    "5407c03055a5f2a0139ca2792e840f80b6a69bd60a58d42266ec262d84ac5c8f"
  ],
  "community-admin-browser-evidence/25-role-switch-cleared-1440.png": [
    301094,
    "d5e9c03051b354bcfd3151037ec78cdd3e3c782af4f24f4b6f8a29600f087450"
  ],
  "community-admin-browser-evidence/44-profile-edit-390.png": [
    56212,
    "747c71d3ee223e85b9077f8e77b3c1785d807cdaf6d58fb91cdc4a59e9111b36"
  ],
  "community-admin-browser-evidence/46-current-subject-relation-1440.png": [
    103895,
    "f7fc8801d0152fd16b6625fc5f1bb8689789099a7375fa63005854c441102576"
  ],
  "community-admin-browser-evidence/46-members-read-1440.png": [
    78605,
    "7f74d3d8e0a0c5da4e61de08499920e98a7cd133e2ac32826223f9087b9a2a18"
  ],
  "community-admin-browser-evidence/46-original-relation-controls-1440.png": [
    104247,
    "24eff11455fac39315673cec282f84a2046ea3c883512936acbbaae9ddc0c239"
  ],
  "community-admin-browser-evidence/46-relation-controls-390.png": [
    56328,
    "fe72dd70b5e31f30b3681f5a73fb295813b03807a1d5d5d9b716dd8c09cefead"
  ],
  "community-admin-browser-evidence/46-subject-denied-cleared-1440.png": [
    86370,
    "870e62ce8381719530a693e1df8416165fefe4d3782cbfcd43d518fc29f17b60"
  ],
  "community-admin-browser-evidence/48-promotion-edit-390.png": [
    95371,
    "8c5d6cc265f5229a55b97c9565dc64a3efb9119c99eb3864660f512c552cb358"
  ],
  "community-admin-browser-evidence/49-detail-1440.png": [
    143188,
    "7a101015b9d7363742156ce113e5510a287f5dd5b3d403c3a1fd7c60fbc73eb7"
  ],
  "community-admin-browser-evidence/50-detail-synthetic-1440.png": [
    142741,
    "c317a1601c2d5f7df3ea1d2a3e08968880ab140f679da5acd7466feacdf47b72"
  ],
  "community-admin-browser-evidence/51-refund-detail-synthetic-1440.png": [
    162563,
    "8340a0ae19fb51a1dc2c07511728e41f02963399cdbd4010006012fb02071e2c"
  ],
  "community-admin-browser-evidence/admission-30-list-1440.png": [
    59152,
    "64e5a227ae638f77de972b0a97e12afffcca2d2032ec78b441a18bde560023d9"
  ],
  "community-admin-browser-evidence/admission-30-return-1440.png": [
    59152,
    "64e5a227ae638f77de972b0a97e12afffcca2d2032ec78b441a18bde560023d9"
  ],
  "community-admin-browser-evidence/admission-60-detail-1440.png": [
    102106,
    "31209da06322b5fc56d8c8d0c6e7fee07516c34018ce442e3dc747fd1c4a2062"
  ],
  "community-admin-browser-evidence/admission-61-controls-1440.png": [
    103940,
    "b7e69427ac66087cbd783745c9cd2681e5abb1a77dba0a6e52efd4d655920e74"
  ],
  "community-admin-browser-evidence/admission-61-controls-390.png": [
    95111,
    "75e560dbd0de631d27b94ae0708870f5f0ef1f49d6c99c1792e27e8093ef71a8"
  ],
  "community-admin-browser-evidence/admission-reopen-30-list-1440.png": [
    59152,
    "64e5a227ae638f77de972b0a97e12afffcca2d2032ec78b441a18bde560023d9"
  ],
  "community-admin-browser-evidence/admission-reopen-30-return-1440.png": [
    59152,
    "64e5a227ae638f77de972b0a97e12afffcca2d2032ec78b441a18bde560023d9"
  ],
  "community-admin-browser-evidence/admission-reopen-60-detail-1440.png": [
    102638,
    "7ed242849edf4dfa55bdac215b61b3404199be3218ee64f129327e7e6fe99f0c"
  ],
  "community-admin-browser-evidence/admission-reopen-61-controls-1440.png": [
    103940,
    "b7e69427ac66087cbd783745c9cd2681e5abb1a77dba0a6e52efd4d655920e74"
  ],
  "community-admin-browser-evidence/admission-reopen-61-controls-390.png": [
    95111,
    "75e560dbd0de631d27b94ae0708870f5f0ef1f49d6c99c1792e27e8093ef71a8"
  ],
  "community-admin-browser-evidence/finance-17-profile-denied-1440.png": [
    100541,
    "fd65e9aa224bb19366f58d17de0392e6ce37b80b900ae432d5b9fb573c5d28d3"
  ],
  "community-admin-browser-evidence/finance-17-profile-list-1440.png": [
    104162,
    "0f1712b54041b36f19827c8ca06077828fccfe2a3d2d2a7d4c0dfd7c4b9268d0"
  ],
  "community-admin-browser-evidence/finance-26-list-1440.png": [
    98540,
    "9bf6b53fe0471809e9ef32667dfe99feafb0fbeaa970d925226b5e6dab3c7bc3"
  ],
  "community-admin-browser-evidence/finance-26-return-1440.png": [
    98524,
    "581318c101d196359543952b082307b9d6e665e9b2b190c323e3260f3b57bad4"
  ],
  "community-admin-browser-evidence/finance-27-denied-1440.png": [
    99005,
    "5ee704e2422690ea94334fcb352f03ada56b5e73621d29f0e5fea5f263ae42e8"
  ],
  "community-admin-browser-evidence/finance-27-list-1440.png": [
    110782,
    "15dc6293fb6621a280a0fca9fe699ecdeeea02d58478b115615b51c6ed6fb098"
  ],
  "community-admin-browser-evidence/finance-27-return-1440.png": [
    110784,
    "f94539d393c641bfb0003fb5dcfb55153714776b67c199dd51a72859a071dce5"
  ],
  "community-admin-browser-evidence/finance-28-platform_audit-list-1440.png": [
    489558,
    "a7fac2626a4fd762bbf82dd4b52a2b6f16bc33c667547fad3cc3e0be401c9e26"
  ],
  "community-admin-browser-evidence/finance-28-platform_customers-list-1440.png": [
    130609,
    "26f8a6e7c22a5a1b04ec6e553faf537b46a98b17b8017aa657b85cc130a34a42"
  ],
  "community-admin-browser-evidence/finance-28-platform_overview-list-1440.png": [
    101693,
    "89d8230f8ae193eb39bd5f5413d3c9613478bb68d4466eced28123dce398ed40"
  ],
  "community-admin-browser-evidence/finance-29-list-1440.png": [
    103747,
    "7dd086a5424b4cc27db294e0a753b839f3620985acf9e5ecada483fd4df0dfa6"
  ],
  "community-admin-browser-evidence/finance-31-list-1440.png": [
    95459,
    "32dc87793351fd3bf138d842d02feb6eeeb41aa1a09b55d04edf2a1ab71b2e09"
  ],
  "community-admin-browser-evidence/finance-31-return-1440.png": [
    95457,
    "8dadc511e4d81c462f35bcf9f6ad1475c896c62154d2e1434526890400029104"
  ],
  "community-admin-browser-evidence/finance-32-detail-1440.png": [
    88706,
    "6bd909fd5b5eb12a2964507c90aa1aeb0628e54930a04d08e3d18e10dc3c2079"
  ],
  "community-admin-browser-evidence/finance-32-return-1440.png": [
    60881,
    "83ec99eb68e4807614c1f354289a57b0742c69e663e324bc6403c835c7516cef"
  ],
  "community-admin-browser-evidence/finance-32-list-1440.png": [
    60881,
    "83ec99eb68e4807614c1f354289a57b0742c69e663e324bc6403c835c7516cef"
  ],
  "community-admin-browser-evidence/finance-32-top-return-1440.png": [
    60881,
    "83ec99eb68e4807614c1f354289a57b0742c69e663e324bc6403c835c7516cef"
  ],
  "community-admin-browser-evidence/finance-33-detail-1440.png": [
    91323,
    "87144ad953f677789bf63d857be783cc8b971662d19b9b16919edf89f43f2443"
  ],
  "community-admin-browser-evidence/finance-33-list-1440.png": [
    62962,
    "f831e2377b1a8fa30807b7e4b4550a98011d72c0e16bef7eaeb2d08e095c77d4"
  ],
  "community-admin-browser-evidence/finance-33-return-1440.png": [
    62962,
    "f831e2377b1a8fa30807b7e4b4550a98011d72c0e16bef7eaeb2d08e095c77d4"
  ],
  "community-admin-browser-evidence/finance-33-return-empty-1440.png": [
    44147,
    "6bb153a9f85583ead28bcfc957cae78ee6f6673acb5b8dc4f7a69e7ddf1ba47f"
  ],
  "community-admin-browser-evidence/finance-33-return-nonempty-1440.png": [
    63969,
    "1bd3bb6234036d649a3ed520f1d52ba8cf05511aee0b9e15ca5eabf45aadfe69"
  ],
  "community-admin-browser-evidence/finance-33-top-return-1440.png": [
    62962,
    "f831e2377b1a8fa30807b7e4b4550a98011d72c0e16bef7eaeb2d08e095c77d4"
  ],
  "community-admin-browser-evidence/finance-34-detail-1440.png": [
    98404,
    "43023a07b423f44a55fc9bce6c9d64c3f078a271886a05689c0989c963b77e1b"
  ],
  "community-admin-browser-evidence/finance-34-list-1440.png": [
    59549,
    "1751c7a9f69c42ef17cf14abc2c46edca368e48a27e2a824468a6a213d7b7250"
  ],
  "community-admin-browser-evidence/finance-34-return-1440.png": [
    59549,
    "1751c7a9f69c42ef17cf14abc2c46edca368e48a27e2a824468a6a213d7b7250"
  ],
  "community-admin-browser-evidence/finance-41-profile-detail-1440.png": [
    112312,
    "f224686f7ce0bce5aed78f13cedf19dd5ae6973a39756bc2812791357a1e2441"
  ],
  "community-admin-browser-evidence/finance-42-profile-edit-1440.png": [
    101767,
    "2ac9021a0b6224c9f119450bb38e3c16ce3424244ebe96a847a636563da4762b"
  ],
  "community-admin-browser-evidence/finance-42-profile-edit-390.png": [
    53578,
    "8fb9f4ccd8aa1b03d62bbc2d6f72e35fa1685b58e86dd9ad1035faf8dab9a603"
  ],
  "community-admin-browser-evidence/finance-52-detail-1440.png": [
    125038,
    "1fdaeb6eae793df9c38b0dcfee61af42223e5b074b889dd52dab243c55d0b08c"
  ],
  "community-admin-browser-evidence/finance-53-edit-1440.png": [
    97955,
    "6994a810b4ff7b20aa117f15934af22d57ad032f77c86803c3cc557a8b62bcd5"
  ],
  "community-admin-browser-evidence/finance-53-readback-1440.png": [
    121579,
    "60e03a5f1a4d5cbaa1de5c3a152965708c8384148894f4ed80e89e261cf67e00"
  ],
  "community-admin-browser-evidence/finance-54-detail-1440.png": [
    110917,
    "5e62076845db23485b40463782451d8a0729535154a35d956a4c030120d6af86"
  ],
  "community-admin-browser-evidence/finance-55-edit-1440.png": [
    136570,
    "0d09c0d1728a02fed62fc2fc4f09891d885cb4a046693669b1c780b9991649d8"
  ],
  "community-admin-browser-evidence/finance-55-edit-390.png": [
    89077,
    "2f7bb5df368311c3ffa2b5d87f796d788f8d1b487353b09849337a42a28f76f9"
  ],
  "community-admin-browser-evidence/finance-55-readback-1440.png": [
    122064,
    "7093ce4e0f2b7903df086bbcd61638075ff8b9eced7973df3d3534f23384c86c"
  ],
  "community-admin-browser-evidence/finance-56-platform_audit-detail-1440.png": [
    131168,
    "e1c164748aca73fbb18c16160365d7f74ec88a62111cae26b5972c99326a0ed9"
  ],
  "community-admin-browser-evidence/finance-56-platform_customers-detail-1440.png": [
    113464,
    "763f71e28a09fe81bc4fd9c804affee241513869b96a61345a2719be7cc47e1d"
  ],
  "community-admin-browser-evidence/finance-56-platform_overview-detail-1440.png": [
    125204,
    "498edddadeab3436d1acbe079555422c0d79211bd55991a95dbe2b14e55e8899"
  ],
  "community-admin-browser-evidence/finance-57-query-1440.png": [
    90240,
    "57b3075223d8ea738bf96e0af3fb2578019777cd6f4d24da1b3b50de12077cad"
  ],
  "community-admin-browser-evidence/finance-58-detail-1440.png": [
    139168,
    "46638569a77e7a99dcd33ac2e22eb6774160036883a1f7cb877bbd8528b710fe"
  ],
  "community-admin-browser-evidence/finance-59-edit-1440.png": [
    120960,
    "ef8bd04008e87bd7f6c9d668c76f187a113d025d398a824fc4a51729fe7729ee"
  ],
  "community-admin-browser-evidence/finance-59-readback-1440.png": [
    140561,
    "e88003362970bda9c4aa026769fc0f43ca24df78ee147570e8b9aad5c3500901"
  ],
  "community-admin-browser-evidence/finance-62-detail-1440.png": [
    108497,
    "7b71c6a55981214f50da84d16700b33b691afd69e14f548e5e3ea3163dc7e191"
  ],
  "community-admin-browser-evidence/finance-65-return-back-1440.png": [
    63969,
    "1bd3bb6234036d649a3ed520f1d52ba8cf05511aee0b9e15ca5eabf45aadfe69"
  ],
  "community-admin-browser-evidence/finance-65-return-detail-1440.png": [
    101275,
    "cc3ac02cab45cf143f342d0e6d9cf986bf48c6bc7f6fc420aca7b6b19acf10b6"
  ],
  "community-admin-browser-evidence/finance-65-top-return-1440.png": [
    63969,
    "1bd3bb6234036d649a3ed520f1d52ba8cf05511aee0b9e15ca5eabf45aadfe69"
  ],
  "community-admin-browser-evidence/finance-66-top-return-1440.png": [
    59549,
    "1751c7a9f69c42ef17cf14abc2c46edca368e48a27e2a824468a6a213d7b7250"
  ],
  "community-admin-browser-evidence/finance-denied-1440.png": [
    42776,
    "84c1a422ea6e116edc2d049e78b2f4661e7fa829c5267a3bddb97f9571992b00"
  ],
  "community-admin-browser-evidence/finance-receipt.json": [
    6768,
    "7ffe9f806f9bb431dfd502c2b3da3b856cea9f2c042ff7aa7afabca35d36061b"
  ],
  "community-admin-browser-evidence/receipt.json": [
    1412,
    "3e64852259b8de922c4f7b439ba69371889d30dca40cfe04cd077c73817a0ced"
  ],
  "community-admin-browser-evidence/split-snapshot-receipt.json": [
    2053,
    "ece14784be70345c90c8ccbf11e97c41037bc23fdfb9db2681723dfebfa98b76"
  ]
}

def require(value, message):
    if not value:
        raise ValueError(message)

def strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'DUPLICATE_JSON_KEY')
            out[k] = v
        return out
    return json.loads(raw, object_pairs_hook=pairs)

def context(env):
    control = env.get('GITHUB_SHA', '')
    require(env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_REPOSITORY') == REPO
            and env.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and re.fullmatch('[0-9a-f]{40}', control)
            and env.get('PREVIEW_CONTROL_SHA') == control
            and env.get('PREVIEW_SOURCE_SHA') == PRODUCT_SHA
            and env.get('PREVIEW_TARGET') == PROFILE
            and env.get('PREVIEW_EVIDENCE_RUN_ID') == str(PRODUCT_RUN)
            and env.get('PREVIEW_ENABLED') == 'true'
            and env.get('IMAGE_BUILD_ENABLED', 'false') == 'false'
            and re.fullmatch('[1-9][0-9]{0,19}', env.get('GITHUB_RUN_ID', ''))
            and re.fullmatch('[1-9][0-9]{0,9}', env.get('GITHUB_RUN_ATTEMPT', ''))
            and env.get('GITHUB_RUN_ID') != str(PRODUCT_RUN),
            'EXACT_FIXED_PRODUCT_CONTROL_CONTEXT_REQUIRED')
    return control

def evidence(run, jobs, artifacts, env, now=None):
    control = context(env)
    now = time.time() if now is None else now
    require(run.get('id') == PRODUCT_RUN and run.get('head_sha') == PRODUCT_SHA
            and run.get('head_branch') == BRANCH and run.get('path') == WORKFLOW
            and run.get('event') == 'push' and run.get('status') == 'completed'
            and run.get('conclusion') == 'success'
            and run.get('repository', {}).get('full_name') == REPO
            and run.get('head_repository', {}).get('full_name') == REPO,
            'FIXED_PRODUCT_PUSH_EVIDENCE_REQUIRED')
    require(type(jobs.get('total_count')) is int and jobs['total_count'] <= 100
            and type(artifacts.get('total_count')) is int and artifacts['total_count'] <= 100,
            'BOUNDED_COMPLETE_EVIDENCE_REQUIRED')
    require(len(jobs.get('jobs', [])) == jobs['total_count']
            and len(artifacts.get('artifacts', [])) == artifacts['total_count'],
            'COMPLETE_EVIDENCE_PAGE_REQUIRED')
    selected = [j for j in jobs['jobs'] if j.get('name') == 'test']
    require(len(selected) == 1 and selected[0].get('id') == PRODUCT_JOB
            and selected[0].get('status') == 'completed'
            and selected[0].get('conclusion') == 'success'
            and any(s.get('name') == 'Complete Phase1 and Phase2 source regression'
                    and s.get('status') == 'completed' and s.get('conclusion') == 'success'
                    for s in selected[0].get('steps', [])), 'FIXED_PRODUCT_TEST_REQUIRED')
    selected = [a for a in artifacts['artifacts']
                if a.get('name') == 'community-phase-integration-evidence']
    require(len(selected) == 1, 'ONE_FIXED_SOURCE_ARTIFACT_REQUIRED')
    a = selected[0]
    binding = a.get('workflow_run', {})
    expiry = datetime.datetime.strptime(a.get('expires_at', ''), '%Y-%m-%dT%H:%M:%SZ').replace(
        tzinfo=datetime.timezone.utc).timestamp()
    require(a.get('id') == ARTIFACT_ID and a.get('expired') is False and expiry > now
            and a.get('size_in_bytes') == ARTIFACT_SIZE
            and a.get('digest') == 'sha256:' + ARTIFACT_SHA256
            and binding.get('id') == PRODUCT_RUN and binding.get('head_sha') == PRODUCT_SHA
            and binding.get('head_branch') == BRANCH
            and binding.get('repository_id') == 1413132159
            and binding.get('head_repository_id') == 1413132159,
            'FIXED_UNEXPIRED_ARTIFACT_BINDING_REQUIRED')
    return dict(status='FIXED_211A9_PRODUCT_EVIDENCE_VERIFIED', control_source_sha=control,
                product_source_sha=PRODUCT_SHA, product_run_id=PRODUCT_RUN,
                product_test_job_id=PRODUCT_JOB, artifact_id=ARTIFACT_ID,
                artifact_sha256=ARTIFACT_SHA256, source_zip_sha256=SOURCE_SHA256,
                source_manifest_sha256=MANIFEST_SHA256, expires_at=a['expires_at'],
                workflow_run_id=env['GITHUB_RUN_ID'],
                workflow_run_attempt=env['GITHUB_RUN_ATTEMPT'],
                appid=APPID, profile=PROFILE, baseUrl=BASE_URL,
                artifact_bytes_reverified=True, upload_performed=False)

def source_files(raw):
    require(hashlib.sha256(raw).hexdigest() == SOURCE_SHA256, 'FIXED_PRODUCT_SOURCE_SHA_REQUIRED')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        items = z.infolist()
        require(0 < len(items) < 2000 and len(items) == len({i.filename for i in items})
                and sum(i.file_size for i in items) < 10000000, 'BOUNDED_SOURCE_REQUIRED')
        manifest_raw = z.read('MANIFEST.json')
        require(hashlib.sha256(manifest_raw).hexdigest() == MANIFEST_SHA256,
                'FIXED_PRODUCT_MANIFEST_SHA_REQUIRED')
        manifest = strict_json(manifest_raw)
        require(manifest.get('format') == 1
                and manifest.get('purpose') == 'OFFLINE_SOURCE_CANDIDATE_NOT_INSTALLABLE'
                and manifest.get('production_payment') == 'HOLD'
                and manifest.get('production_deployment') == 'HOLD'
                and set(z.namelist()) == set(manifest['files']) | {'MANIFEST.json'},
                'COMPLETE_PRODUCT_MANIFEST_REQUIRED')
        files = {}
        for item in items:
            p = PurePosixPath(item.filename)
            require(not p.is_absolute() and '..' not in p.parts and chr(92) not in item.filename
                    and str(p) == item.filename and stat.S_ISREG(item.external_attr >> 16),
                    'SAFE_REGULAR_PRODUCT_FILE_REQUIRED')
            data = z.read(item)
            require(item.filename == 'MANIFEST.json'
                    or hashlib.sha256(data).hexdigest() == manifest['files'][item.filename],
                    'PRODUCT_FILE_SHA_REQUIRED')
            files[item.filename] = data
    config = strict_json(files['clients/community-mini/project.config.json'])
    require(config.get('appid') == APPID and config.get('compileType') == 'miniprogram'
            and config.get('miniprogramRoot') == './', 'FIXED_PRODUCT_APPID_REQUIRED')
    require(strict_json(files['deploy/community-preview/endpoint-profiles.json']).get(PROFILE) == BASE_URL,
            'FIXED_PRODUCT_ENDPOINT_REQUIRED')
    return files

def archive_source(raw):
    require(len(raw) == ARTIFACT_SIZE and hashlib.sha256(raw).hexdigest() == ARTIFACT_SHA256,
            'FIXED_ARTIFACT_BYTES_SHA_REQUIRED')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        require(len(z.infolist()) == len(ARTIFACT_MEMBERS)
                and set(z.namelist()) == set(ARTIFACT_MEMBERS),
                'FIXED_ARTIFACT_MEMBERS_REQUIRED')
        for item in z.infolist():
            size, digest = ARTIFACT_MEMBERS[item.filename]
            require(item.file_size == size and not item.is_dir()
                    and hashlib.sha256(z.read(item)).hexdigest() == digest,
                    'FIXED_ARTIFACT_MEMBER_BYTES_SHA_REQUIRED')
        source = z.read('community-stage-source.zip')
    source_files(source)
    return source

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def read_api(suffix):
    url = 'https://api.github.com/repos/' + REPO + suffix
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(Request(url, headers={'Accept': 'application/vnd.github+json',
                                          'User-Agent': 'community-fixed-product-preview'}), timeout=10) as r:
        require(r.status == 200 and r.geturl() == url, 'EXACT_GITHUB_RESPONSE_REQUIRED')
        data = r.read(1048577)
        require(len(data) <= 1048576, 'EVIDENCE_SIZE_LIMIT')
        return strict_json(data)

def download_archive(token):
    # The repository token is used ONLY for this fixed GitHub API request.
    # Signed storage GET never receives Authorization; redirects are not followed.
    from urllib.error import HTTPError
    require(bool(token), 'EXISTING_GITHUB_TOKEN_REQUIRED')
    url = 'https://api.github.com/repos/' + REPO + '/actions/artifacts/' + str(ARTIFACT_ID) + '/zip'
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(Request(url, headers={'Authorization': 'Bearer ' + token,
                              'Accept': 'application/vnd.github+json'}), timeout=10)
    except HTTPError as exc:
        require(exc.code == 302, 'FIXED_ARTIFACT_REDIRECT_REQUIRED')
        location = exc.headers.get('Location', '')
        exc.close()
    else:
        response.close()
        raise ValueError('FIXED_ARTIFACT_REDIRECT_REQUIRED')
    parsed = urlparse(location)
    require(parsed.scheme == 'https' and parsed.hostname
            and not parsed.username and not parsed.password and parsed.port in (None, 443)
            and not parsed.fragment
            and any(parsed.hostname.endswith(s) for s in (
                '.blob.core.windows.net', '.actions.githubusercontent.com',
                '.githubusercontent.com', '.s3.amazonaws.com')),
            'GITHUB_ARTIFACT_STORAGE_REQUIRED')
    with opener.open(Request(location), timeout=30) as r:
        require(r.status == 200 and r.geturl() == location, 'ARTIFACT_RESPONSE_REQUIRED')
        data = r.read(MAX_BYTES + 1)
        require(len(data) <= MAX_BYTES, 'ARTIFACT_SIZE_LIMIT')
        return data

def write_new(path, data):
    with open(path, 'xb') as f:
        os.chmod(path, 0o600)
        f.write(data)

def read_regular(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'REGULAR_INPUT_REQUIRED')
        with os.fdopen(fd, 'rb', closefd=False) as f:
            data = f.read(limit + 1)
        require(len(data) <= limit, 'INPUT_SIZE_LIMIT')
        return data
    finally:
        os.close(fd)

def paths(env):
    suffix = env['GITHUB_RUN_ID'] + '-' + env['GITHUB_RUN_ATTEMPT']
    temp = Path(env['RUNNER_TEMP']).resolve()
    return temp / ('community-mini-product-source-' + suffix), temp / ('community-mini-product-context-' + suffix + '.json')

def verify_receipt(receipt, env):
    control = context(env)
    require(receipt.get('status') == 'FIXED_211A9_PRODUCT_EVIDENCE_VERIFIED'
            and receipt.get('control_source_sha') == control
            and receipt.get('product_source_sha') == PRODUCT_SHA
            and receipt.get('product_run_id') == PRODUCT_RUN
            and receipt.get('product_test_job_id') == PRODUCT_JOB
            and receipt.get('artifact_id') == ARTIFACT_ID
            and receipt.get('artifact_sha256') == ARTIFACT_SHA256
            and receipt.get('source_zip_sha256') == SOURCE_SHA256
            and receipt.get('source_manifest_sha256') == MANIFEST_SHA256
            and receipt.get('workflow_run_id') == env['GITHUB_RUN_ID']
            and receipt.get('workflow_run_attempt') == env['GITHUB_RUN_ATTEMPT']
            and receipt.get('appid') == APPID and receipt.get('profile') == PROFILE
            and receipt.get('baseUrl') == BASE_URL and receipt.get('artifact_bytes_reverified') is True
            and receipt.get('upload_performed') is False, 'FIXED_PRODUCT_RECEIPT_REQUIRED')
    expiry = datetime.datetime.strptime(receipt.get('expires_at', ''), '%Y-%m-%dT%H:%M:%SZ').replace(
        tzinfo=datetime.timezone.utc).timestamp()
    require(expiry > time.time(), 'FIXED_PRODUCT_ARTIFACT_EXPIRED')
    return control

def stage(source, receipt, env):
    verify_receipt(receipt, env)
    files = source_files(source)
    destination, context_file = paths(env)
    require(not destination.exists() and not destination.is_symlink()
            and not context_file.exists() and not context_file.is_symlink(), 'PRODUCT_OUTPUT_ALREADY_EXISTS')
    import shutil
    temp = Path(tempfile.mkdtemp(prefix='.fixed-product-', dir=destination.parent))
    try:
        for name, data in files.items():
            p = temp / name
            p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_new(p, data)
        os.rename(temp, destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    receipt = dict(receipt, source_root=str(destination))
    write_new(context_file, (json.dumps(receipt, sort_keys=True) + '\n').encode())
    return receipt

def identity(env):
    require(env.get('COMMUNITY_FIXED_PRODUCT_PREVIEW', 'false') in ('true', 'false'), 'EXACT_PRODUCT_MODE_REQUIRED')
    if env.get('COMMUNITY_FIXED_PRODUCT_PREVIEW', 'false') != 'true':
        require(not env.get('COMMUNITY_PREVIEW_PRODUCT_CONTEXT'), 'UNEXPECTED_PRODUCT_CONTEXT')
        return dict(product_source_sha=env.get('GITHUB_SHA'), control_source_sha=env.get('GITHUB_SHA'),
                    source_root=None, fixed_product=False)
    destination, context_file = paths(env)
    require(env.get('COMMUNITY_PREVIEW_PRODUCT_CONTEXT') == str(context_file), 'EXACT_PRODUCT_CONTEXT_PATH_REQUIRED')
    receipt = strict_json(read_regular(context_file, 16384))
    verify_receipt(receipt, env)
    require(receipt.get('source_root') == str(destination) and not destination.is_symlink(),
            'EXACT_PRODUCT_SOURCE_ROOT_REQUIRED')
    manifest_raw = read_regular(destination / 'MANIFEST.json', 1000000)
    require(hashlib.sha256(manifest_raw).hexdigest() == MANIFEST_SHA256, 'FIXED_PRODUCT_MANIFEST_SHA_REQUIRED')
    manifest = strict_json(manifest_raw)['files']
    require(not (destination / 'clients').is_symlink(), 'PRODUCT_SOURCE_SYMLINK_DENIED')
    mini = destination / 'clients/community-mini'
    require(not mini.is_symlink() and mini.is_dir(), 'PRODUCT_SOURCE_SYMLINK_DENIED')
    expected = {k[len('clients/community-mini/'):]: v for k, v in manifest.items()
                if k.startswith('clients/community-mini/')}
    actual = {}
    for p in mini.rglob('*'):
        require(not p.is_symlink(), 'PRODUCT_SOURCE_SYMLINK_DENIED')
        if p.is_file():
            actual[p.relative_to(mini).as_posix()] = hashlib.sha256(read_regular(p, 10000000)).hexdigest()
        else:
            require(p.is_dir(), 'PRODUCT_SOURCE_REGULAR_REQUIRED')
    require(actual == expected, 'FIXED_PRODUCT_SOURCE_CHANGED')
    prepared = {k: v for k, v in expected.items() if not k.endswith('.test.cjs')}
    prepared['app.js'] = CONNECTED_APP_SHA256
    require(len(prepared) == 27, 'FIXED_PREPARED_SOURCE_SET_REQUIRED')
    return dict(product_source_sha=PRODUCT_SHA, control_source_sha=receipt['control_source_sha'],
                source_root=str(destination), prepared_files=prepared, fixed_product=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('admit', 'stage', 'identity'))
    args = parser.parse_args()
    env = os.environ
    if args.operation == 'identity':
        print(json.dumps(identity(env), sort_keys=True))
        return
    context(env)
    if args.operation == 'admit':
        require(not Path('fixed-product-source.zip').exists() and not Path('fixed-product-receipt.json').exists(),
                'PRODUCT_ADMISSION_OUTPUT_ALREADY_EXISTS')
        prefix = '/actions/runs/' + str(PRODUCT_RUN)
        receipt = evidence(read_api(prefix), read_api(prefix + '/jobs?per_page=100'),
                           read_api(prefix + '/artifacts?per_page=100'), env)
        source = archive_source(download_archive(env.get('GITHUB_TOKEN', '')))
        write_new('fixed-product-source.zip', source)
        write_new('fixed-product-receipt.json', (json.dumps(receipt, sort_keys=True) + '\n').encode())
        print('FIXED_211A9_PRODUCT_SOURCE_VERIFIED_NO_UPLOAD')
    else:
        root = Path(env['RUNNER_TEMP']) / ('community-mini-fixed-input-' + env['GITHUB_RUN_ID'] + '-' + env['GITHUB_RUN_ATTEMPT'])
        stage(read_regular(root / 'fixed-product-source.zip', MAX_BYTES),
              strict_json(read_regular(root / 'fixed-product-receipt.json', 16384)), env)
        print('FIXED_211A9_PRODUCT_STAGED_NO_UPLOAD')

def safe_failure_reason(exc):
    # Publish only fixed non-sensitive diagnoses, never URLs, token values or traces.
    allowed = frozenset(('FIXED_ARTIFACT_MEMBER_BYTES_SHA_REQUIRED', 'FIXED_ARTIFACT_MEMBERS_REQUIRED', 'FIXED_ARTIFACT_BYTES_SHA_REQUIRED',
        'FIXED_PRODUCT_SOURCE_SHA_REQUIRED', 'FIXED_PRODUCT_MANIFEST_SHA_REQUIRED',
        'FIXED_PRODUCT_PUSH_EVIDENCE_REQUIRED', 'FIXED_PRODUCT_TEST_REQUIRED',
        'FIXED_UNEXPIRED_ARTIFACT_BINDING_REQUIRED', 'GITHUB_ARTIFACT_STORAGE_REQUIRED',
        'FIXED_ARTIFACT_REDIRECT_REQUIRED', 'EXACT_FIXED_PRODUCT_CONTROL_CONTEXT_REQUIRED'))
    if type(exc) is ValueError and str(exc) in allowed:
        return str(exc)
    from urllib.error import HTTPError
    if isinstance(exc, HTTPError) and type(exc.code) is int and 400 <= exc.code <= 599:
        return 'HTTP_STATUS_' + str(exc.code)
    return 'UNCLASSIFIED_SAFE_FAILURE'

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('FIXED_PRODUCT_PREVIEW_ADMISSION_FAILED: ' + safe_failure_reason(exc))

