"""Fixed 4f same-source product admission for the ORIGINAL preview workflow, never deployment.
GITHUB_SHA remains the control revision. No arbitrary artifact/ref/product is accepted.
"""
import argparse, datetime, hashlib, io, json, os, re, stat, tempfile, time, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
BRANCH = 'feature/chatgpt-community-wechat-sp-offline-20261017'
WORKFLOW = '.github/workflows/chatgpt-community-wechat-sp-offline.yml'
PRODUCT_SHA = '4f1c3aea2c01ead25c5bd075535b8ce7bd9cd5f5'
PRODUCT_RUN = 41101879920
PRODUCT_JOB = 124220361504
ARTIFACT_ID = 13000357097
ARTIFACT_SIZE = 13028520
ARTIFACT_SHA256 = 'b6c49a917abe9bb07683ad41b9b98d2975a79a0be8e6f59714db05debf8c0560'
SOURCE_SHA256 = '0400d992809e09f62c4a80cb9ce011dbfc99b8842ca8f31b34303377a7eb5af1'
MANIFEST_SHA256 = '9f203a9f0448b26b368fc0b39fbe5ec043900a2ef64ced38984e63d5ab5ef86e'
APPID = 'wx1d5f8873eaea5392'
PROFILE = 'uk-path-candidate'
BACKEND_SHA = '4f1c3aea2c01ead25c5bd075535b8ce7bd9cd5f5'
COMPATIBILITY_SHA256 = '548d9cd1c92d14ad848cb83205338333ecda0dd45718f0df7de4831063d61367'
COMPATIBILITY = 'EXACT_SOURCE_MATCH'
BASE_URL = 'https://uk.wenwenwenyiyiyi.work/community-preview'
CONNECTED_APP_SHA256 = '07eaedb76bc73f278eeab7235cf2f921cee0c875f890fdc26c82fb4e4699b42e'
BACKEND_IMAGE_ID = 'sha256:9ceb64b5e1f4b8a677d200e7e3aa73182253e3c1ec116f979c9c4a8fd0772a6c'
MAX_BYTES = 20000000
# Exact actual product evidence archive; no arbitrary extra member admission.
ARTIFACT_MEMBERS = {
  "community-tests.log": [
    621070,
    "e93a2dea787f8c2e83babaa59ce4394d55f8a8d42ff71086d8b618454bc3786a"
  ],
  "stage5-tests.log": [
    45344,
    "15856607e5e66d0ccc911c80463b39e26ea4261eb89182cd52440890c0dee8f0"
  ],
  "community-stage-source.zip": [
    6625013,
    "0400d992809e09f62c4a80cb9ce011dbfc99b8842ca8f31b34303377a7eb5af1"
  ],
  "community-admin-browser-evidence/16-community-home-1440.png": [
    222829,
    "9ef7897f0c7f8eae7a3c10a2c169a3ec8cc12d0b234271b5424e48352f32195d"
  ],
  "community-admin-browser-evidence/16-community-home-390.png": [
    160800,
    "3f55528a7a910a66e16b813ea0fd5474f809070944b32b37dc6ec8f6d7c8764b"
  ],
  "community-admin-browser-evidence/16-logout-neutral-1440.png": [
    129438,
    "5a8b69486a4df1f6e5a6a756f484a1c4a6f85487f0b1613bf56f96096de54aa7"
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
    81588,
    "44e028865b258e9af96b8efbe7cde41708e3c10c3b3c648b1980f708b103c337"
  ],
  "community-admin-browser-evidence/19-detail-1440.png": [
    129546,
    "f0845d7d429878ac57a2a0de9787d9c7dfe2e24d43fcb395e140bffb37e29dd4"
  ],
  "community-admin-browser-evidence/19-list-1440.png": [
    109946,
    "1d06a4706274e29c721a8abeb3534749fc92569551afeea90c4991d4feab4bf4"
  ],
  "community-admin-browser-evidence/19-return-1440.png": [
    109946,
    "1d06a4706274e29c721a8abeb3534749fc92569551afeea90c4991d4feab4bf4"
  ],
  "community-admin-browser-evidence/20-before-query-1440.png": [
    143156,
    "9ddc5ca1e0c86f47ea6a88400a2b16d17ad0e1bed9389b9e431e81da8bbb8bda"
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
    129648,
    "1b683cac6329a922eb4e81fb8e7a983bdf39bf9736470c99519c6de1e694ad41"
  ],
  "community-admin-browser-evidence/20-nonempty-synthetic-1440.png": [
    133158,
    "77589ded9af224a38b352cf1f2580f4f144e68e5965d831915728240cde833a7"
  ],
  "community-admin-browser-evidence/20-return-1440.png": [
    129640,
    "9818408bbbf50b6db502a7c0c3efa0f833d3820f9068c02a6712fd140ff8cfa5"
  ],
  "community-admin-browser-evidence/21-denied-cleared-1440.png": [
    94960,
    "e3d0b4e0a3ea68f7b7f8e388b7c030e7619db66054eb56ee2220a51fcd78a8c3"
  ],
  "community-admin-browser-evidence/21-detail-1440.png": [
    121401,
    "3b0ec338c272d65461c70076476545df3bb3410b546db2c3e0c813a5cfd5b1c5"
  ],
  "community-admin-browser-evidence/21-list-1440.png": [
    120571,
    "73e88164aedd0370897833cceb73c20e8c709058ba1fb8967e2c825d327f4ebc"
  ],
  "community-admin-browser-evidence/21-return-1440.png": [
    120556,
    "149d35b32f4f340c305e52c5d35b604cdca8967e4821bbf97a07a6608d407ca7"
  ],
  "community-admin-browser-evidence/21-state-readback-1440.png": [
    121716,
    "0683f8209e7fbfb9ad10de7b51d94079e5f0629fa8adf40a9a4b31608fe100e2"
  ],
  "community-admin-browser-evidence/22-denied-cleared-1440.png": [
    98562,
    "0ada505b077b57fbef066a2db7a28858573a36b8a8de06e8cc942f895bb6f5b5"
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
    107867,
    "d26c8a14e362cc3d53ac7c82f20593bb87c9f68140adc949d58cad58a00862ea"
  ],
  "community-admin-browser-evidence/23-return-synthetic-1440.png": [
    118898,
    "2107cd20c6013af91b899f2bbd469b844f4901f8622b45fde70b9a4c73d6644f"
  ],
  "community-admin-browser-evidence/23-list-synthetic-1440.png": [
    114981,
    "45267a01b04461621d8832a4673497efc31820a99d9de017d3c4b353315adc32"
  ],
  "community-admin-browser-evidence/24-refund-denied-cleared-1440.png": [
    108105,
    "d777780bb71b41417acbd9535c0e35dcb8f9ef6d9913ddc8caf8b70a1ae91008"
  ],
  "community-admin-browser-evidence/24-refund-list-synthetic-1440.png": [
    150700,
    "57cabd1cd620474eb17802a982a29a0d1fc27eb3742152345935a3c80bfb95a2"
  ],
  "community-admin-browser-evidence/24-refund-return-1440.png": [
    150698,
    "52acaa39e8fef255b30021f1154f372fbeb4b504745c9b90b9ac9357aef8ce06"
  ],
  "community-admin-browser-evidence/25-logout-neutral-1440.png": [
    129441,
    "137a493373a61550dcb3094473d87a40648198e6aea315429f1cc171fea387b5"
  ],
  "community-admin-browser-evidence/25-platform-home-1440.png": [
    302415,
    "eac2c6d270b2914da5a79049c339ddd2be0207ce5c29a2297abccc6e42fbbd88"
  ],
  "community-admin-browser-evidence/25-platform-home-390.png": [
    219761,
    "5407c03055a5f2a0139ca2792e840f80b6a69bd60a58d42266ec262d84ac5c8f"
  ],
  "community-admin-browser-evidence/25-role-switch-cleared-1440.png": [
    305915,
    "3aec56a930bb1f3d2620b1acb43be3804ffc3ecfc5de7dd886f9cca36e821a47"
  ],
  "community-admin-browser-evidence/44-profile-edit-390.png": [
    56212,
    "747c71d3ee223e85b9077f8e77b3c1785d807cdaf6d58fb91cdc4a59e9111b36"
  ],
  "community-admin-browser-evidence/46-current-subject-relation-1440.png": [
    105027,
    "759c86c454bfcd6271dd3c2ee58c6dd4d3eabb431f58faa717ae6098a95fa708"
  ],
  "community-admin-browser-evidence/46-members-read-1440.png": [
    78483,
    "7088e42e6a1c1bf7668fd0490eb6119dc3bd5afd294939dda4a304e5dfbea226"
  ],
  "community-admin-browser-evidence/46-original-relation-controls-1440.png": [
    104117,
    "f52fc8734486c4789d5dfe5477b0ccca02320280f9c5aecc6a8d61466137da59"
  ],
  "community-admin-browser-evidence/46-relation-controls-390.png": [
    56223,
    "659022ecf7ead3173ec9d4b9fd145382dd9b38cb6160b251e73b58f14438d12a"
  ],
  "community-admin-browser-evidence/46-subject-denied-cleared-1440.png": [
    87193,
    "c141c49d6c301621899b9303262fd2f7ed58624a20dae95d16b31928d4c28d0c"
  ],
  "community-admin-browser-evidence/48-promotion-edit-390.png": [
    95371,
    "8c5d6cc265f5229a55b97c9565dc64a3efb9119c99eb3864660f512c552cb358"
  ],
  "community-admin-browser-evidence/49-detail-1440.png": [
    143645,
    "397623df95fd1828ec23c9c512648db658da8e564a1cf5e43c8b4a2f6c6a9763"
  ],
  "community-admin-browser-evidence/50-detail-synthetic-1440.png": [
    146723,
    "84ebd5545bb5d430faf5f3789e1777a297f6ec16c1127882dad2988032ea571c"
  ],
  "community-admin-browser-evidence/51-refund-detail-synthetic-1440.png": [
    166671,
    "35598d31bf884a68c33e1a0c34de275d9fc009221ca173712cd545aa5ae4c72a"
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
    103585,
    "7239b245dde17d72e12f52fa253a7be167b57cd0a59c4bba7d58de24c62b286e"
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
    102750,
    "c6966622d76c1f3ef503626131d48fadb29e182f8215b00f007f6de386de10a1"
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
    488531,
    "a20a29a48475c67cf795d76baead86f34316b1ba6f7d41cc438f2d7ec4f5c1df"
  ],
  "community-admin-browser-evidence/finance-28-platform_customers-list-1440.png": [
    130240,
    "bef14a4465a9ec730b7157d80939db8993fd215dbbebac1d2d046f9c41280e63"
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
  "community-admin-browser-evidence/finance-32-list-1440.png": [
    60881,
    "83ec99eb68e4807614c1f354289a57b0742c69e663e324bc6403c835c7516cef"
  ],
  "community-admin-browser-evidence/finance-32-return-1440.png": [
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
    97932,
    "7cc630c54ebc7e8ca9f1e489606b83071b9cb4c997d3864eba17f4fd4a07deb4"
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
    131242,
    "4203445d4b8ae06a9b41886a38faf5b9e05ec59d8c1ca13751d5dd64c82ee10d"
  ],
  "community-admin-browser-evidence/finance-56-platform_customers-detail-1440.png": [
    113695,
    "429378bd6c2a1af26a1d6ca54589174cfbe57bc92e498c0aedd7bb09c0a2bc23"
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
  "community-admin-browser-evidence/finance-denied-1440.png": [
    42776,
    "84c1a422ea6e116edc2d049e78b2f4661e7fa829c5267a3bddb97f9571992b00"
  ],
  "community-admin-browser-evidence/finance-66-top-return-1440.png": [
    59549,
    "1751c7a9f69c42ef17cf14abc2c46edca368e48a27e2a824468a6a213d7b7250"
  ],
  "community-admin-browser-evidence/finance-receipt.json": [
    6768,
    "7ffe9f806f9bb431dfd502c2b3da3b856cea9f2c042ff7aa7afabca35d36061b"
  ],
  "community-admin-browser-evidence/receipt.json": [
    1412,
    "8be06a52d4e54c7f1e5327c9f407aed095e59d4624e4a2783635088c973feab2"
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

def evidence(run, jobs, artifacts, env, now=None, archive_raw=None):
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
            and (any(s.get('name') == 'Complete Phase1 and Phase2 source regression'
                    and s.get('status') == 'completed' and s.get('conclusion') == 'success'
                    for s in selected[0].get('steps', []))
                 or (selected[0].get('steps') == [] and archive_raw is not None
                     and bool(archive_source(archive_raw)))), 'FIXED_PRODUCT_TEST_REQUIRED')
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
    return dict(status='FIXED_4F_SAME_SOURCE_PRODUCT_EVIDENCE_VERIFIED', control_source_sha=control,
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
    require(receipt.get('status') == 'FIXED_4F_SAME_SOURCE_PRODUCT_EVIDENCE_VERIFIED'
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

def compatibility_binding():
    raw = read_regular(Path(__file__).resolve().parents[1] /
                       'deploy/community-preview/native-backend-compatibility.json', 300000)
    require(hashlib.sha256(raw).hexdigest() == COMPATIBILITY_SHA256,
            'FIXED_COMPATIBILITY_PROOF_REQUIRED')
    proof = strict_json(raw)
    # This is a new exact same-source image binding, never a renamed cross-version proof.
    # It does not establish installation or live health; the original health gate follows.
    require(proof.get('schema') == 1
            and proof.get('status') == 'EXACT_SOURCE_IMAGE_BINDING_NOT_RUNTIME_ADMISSION'
            and proof.get('frontend_source_sha') == PRODUCT_SHA
            and proof.get('backend_source_sha') == BACKEND_SHA == PRODUCT_SHA
            and proof.get('compatibility') == COMPATIBILITY == 'EXACT_SOURCE_MATCH'
            and proof.get('backend_image_id') == BACKEND_IMAGE_ID
            and all(proof.get('archives', {}).get(side, {}).get('sha256') == SOURCE_SHA256
                    and proof.get('archives', {}).get(side, {}).get('manifest_sha256') == MANIFEST_SHA256
                    and proof.get('archives', {}).get(side, {}).get('all_manifest_members_verified') is True
                    for side in ('frontend', 'backend'))
            and proof.get('source_scope_result') == 'SCOPED_PASS'
            and proof.get('all_delta_classified') is True and proof.get('unknown_delta') == []
            and proof.get('complete_classified_delta') == []
            and proof.get('runtime_admission') == 'REQUIRES_FRESH_EXACT_SOURCE_HEALTH',
            'FIXED_COMPATIBILITY_PROOF_REQUIRED')
    return dict(backend_source_sha=BACKEND_SHA, compatibility=COMPATIBILITY,
                compatibility_sha256=COMPATIBILITY_SHA256)

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
    require(len(prepared) == 36
            and prepared.get('assets/community-demo-storefront-v1.jpg') ==
            'f8e066fc2153b5beff1ae65faf9be5383d877eb77336cc5e16c90468b13b65b6',
            'FIXED_PREPARED_SOURCE_SET_REQUIRED')
    return dict(product_source_sha=PRODUCT_SHA, control_source_sha=receipt['control_source_sha'],
                source_root=str(destination), prepared_files=prepared, fixed_product=True,
                **compatibility_binding())

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
        # Exact pinned archive includes both original successful test logs.
        raw = download_archive(env.get('GITHUB_TOKEN', ''))
        receipt = evidence(read_api(prefix), read_api(prefix + '/jobs?per_page=100'),
                           read_api(prefix + '/artifacts?per_page=100'), env, archive_raw=raw)
        source = archive_source(raw)
        write_new('fixed-product-source.zip', source)
        write_new('fixed-product-receipt.json', (json.dumps(receipt, sort_keys=True) + '\n').encode())
        print('FIXED_4F_PRODUCT_SOURCE_VERIFIED_NO_UPLOAD')
    else:
        root = Path(env['RUNNER_TEMP']) / ('community-mini-fixed-input-' + env['GITHUB_RUN_ID'] + '-' + env['GITHUB_RUN_ATTEMPT'])
        stage(read_regular(root / 'fixed-product-source.zip', MAX_BYTES),
              strict_json(read_regular(root / 'fixed-product-receipt.json', 16384)), env)
        print('FIXED_4F_PRODUCT_STAGED_NO_UPLOAD')

def safe_failure_reason(exc):
    # Publish only fixed non-sensitive diagnoses, never URLs, token values or traces.
    allowed = frozenset(('FIXED_ARTIFACT_MEMBER_BYTES_SHA_REQUIRED', 'FIXED_ARTIFACT_MEMBERS_REQUIRED', 'FIXED_ARTIFACT_BYTES_SHA_REQUIRED',
        'FIXED_PRODUCT_SOURCE_SHA_REQUIRED', 'FIXED_PRODUCT_MANIFEST_SHA_REQUIRED',
        'FIXED_COMPATIBILITY_PROOF_REQUIRED',
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

