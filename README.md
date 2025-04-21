<p align="center"><img src= "TBD" alt="SQLBot" width="300" /></p>
<h3 align="center">Chat with your SQL database</h3>
<p align="center">
  <a href="https://www.gnu.org/licenses/gpl-3.0.html#license-text"><img src="https://img.shields.io/github/license/1Panel-dev/SQLBot?color=%231890FF" alt="License: GPL v3"></a>
  <a href="https://github.com/1Panel-dev/SQLBot/releases/latest"><img src="https://img.shields.io/github/v/release/1Panel-dev/SQLBot" alt="Latest release"></a>
  <a href="https://github.com/1Panel-dev/SQLBot"><img src="https://img.shields.io/github/stars/1Panel-dev/SQLBot?color=%231890FF&style=flat-square" alt="Stars"></a>    
  <a href="https://hub.docker.com/r/1panel/SQLbot"><img src="https://img.shields.io/docker/pulls/1panel/SQLBot?label=downloads" alt="Download"></a><br/>
 [<a href="/README_CN.md">中文(简体)</a>] | [<a href="/README.md">English</a>] 
</p>
<hr/>

SQLChat allows you to interact with your SQL database through advanced Text-to-SQL technology. This capability is powered by Large Language Models (LLMs) and Retrieval-Augmented Generation (RAG).

- **TBD**: TBD.
- **TBD**: TBD.
- **TBD**: TBD.
- **TBD**: TBD.

## Quick start

Execute the script below to start a SQLBot container using Docker:

```bash
docker run -d --name=sqlbot --restart=always -p 8080:8080 -v ~/.sqlbot:/var/lib/postgresql/data 1panel/sqlbot
```

Access SQLBot web interface at `http://your_server_ip:8080` with default admin credentials:

- username: admin
- password: SQLBot@123..

## Screenshots

<table style="border-collapse: collapse; border: 1px solid black;">
  <tr>
    <td style="padding: 5px;background-color:#fff;"><img src= "TBD" alt="SQLBot Demo1"   /></td>
    <td style="padding: 5px;background-color:#fff;"><img src= "TBD" alt="SQLBot Demo2"   /></td>
  </tr>
  <tr>
    <td style="padding: 5px;background-color:#fff;"><img src= "TBD" alt="SQLBot Demo3"   /></td>
    <td style="padding: 5px;background-color:#fff;"><img src= "TBD" alt="SQLBot Demo4"   /></td>
  </tr>
</table>

## Technical stack

- Frontend：[Vue.js](https://vuejs.org/)
- Backend：[Python / Django](https://www.djangoproject.com/)
- Database：[PostgreSQL + pgvector](https://www.postgresql.org/)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=1Panel-dev/SQLBot&type=Date)](https://star-history.com/#1Panel-dev/SQLBot&Date)

## License

Licensed under The GNU General Public License version 3 (GPLv3)  (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

<https://www.gnu.org/licenses/gpl-3.0.html>

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
